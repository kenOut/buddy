"""The Quest evaluation pipeline (Phase 3B Stage 5):

    QuestAttempt (SUBMITTED)
        -> deterministic evaluation (QuestEvaluationCriterion)
        -> objective evaluation evidence
        -> AI interpretation (reuses the Phase 3A AIProvider abstraction)
        -> CapabilityEvaluation
        -> CapabilityEvidence
        -> CapabilityProfile (via the existing Phase 3A aggregation)
        -> QuestAttempt (COMPLETED)

Everything here runs in one call (`evaluate_attempt`), triggered by
`POST /quest-attempts/{id}/evaluate` — unlike Mission, where deterministic
evidence is created at submit time and AI evidence separately at evaluate
time, Quest's richer QuestEvaluationCriterion model makes it natural to
run deterministic + AI evaluation together as a single pipeline. This
does not touch quest_attempt_service.submit_attempt at all.

AI is never the source of truth for objective correctness: deterministic
evaluation runs first and its result (`objective_passed`/`objective_score`)
is handed to the AI as an already-decided fact, exactly like Mission's
`objective_passed`/`objective_score` in ai_evaluation_service.py. The AI
interprets qualitative signals (reasoning/solution quality) and is never
asked to re-grade what was deterministically checkable.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import (
    CapabilityEvaluation,
    CapabilityEvidence,
    Employee,
    Quest,
    QuestAttempt,
    QuestEvaluationCriterion,
)
from app.schemas.ai_evaluation import AIEvaluationResponse
from app.services import (
    capability_aggregation,
    capability_service,
    quest_capability_service,
    quest_evaluation_criterion_service,
    quest_task_service,
    readiness_service,
)
from app.services.ai_evaluation_service import AIEvaluationRejected
from app.services.ai_provider import (
    AIProviderError,
    QuestAIEvaluationContext,
    QuestDeterministicCriterionResult,
    get_ai_provider,
)
from app.services.evaluation_context import (
    EvaluationContext,
    TroubleshootWorkspaceContext,
    build_evaluation_context,
)

DETERMINISTIC_EVIDENCE_TYPE = "quest_objective_result"

ACTIVE_STATUSES = ("SUBMITTED", "EVALUATING")


class QuestAttemptNotEvaluableError(Exception):
    """Raised when evaluation is requested against an attempt that isn't
    SUBMITTED or currently EVALUATING (e.g. still IN_PROGRESS, or already
    COMPLETED with no recoverable evaluation record)."""


class NoCapabilityMappingError(Exception):
    """Raised when a quest has zero QuestCapability mappings — there is
    nothing honest for the AI to assess, so evaluation completes
    deterministically only (see evaluate_attempt's handling)."""


# =====================================================================
# Deterministic evaluation
# =====================================================================


@dataclass
class DeterministicCriterionOutcome:
    criterion_id: str
    criterion_type: str
    name: str
    # None means "not deterministically checkable from the current
    # submission schema" — never a fabricated pass/fail.
    passed: bool | None
    score: float
    max_score: float
    evidence: str


@dataclass
class TroubleshootDeterministicFacts:
    """Phase 7 Stage 4C — explicit, named structural facts about a
    Troubleshoot attempt's structured payload. Deliberately narrow:
    presence (was a field filled in) is kept distinct from correctness
    (does it match a server-defined answer), and nothing here is
    derived from interaction activity (evidence-view counts, hypothesis
    counts, confidence, timing) — see the hard rule in
    quest_evaluation_service's module docstring / Stage 4C spec §11.

    `root_cause_matches_expected` is `None` when the quest defines no
    DETERMINISTIC criterion with a non-empty `expected_answer` — there
    is nothing to have passed or failed, so it is never fabricated as
    True or False. It is populated only when the structured
    `diagnosis.root_cause` field is what satisfied that criterion.
    """

    root_cause_present: bool
    proposed_fix_present: bool
    root_cause_matches_expected: bool | None


@dataclass
class DeterministicEvaluationResult:
    criterion_outcomes: list[DeterministicCriterionOutcome]
    objective_passed: bool
    objective_score: float  # 0-100
    qualitative_criterion_descriptions: list[str]
    # None for GENERAL (and any workspace_type without structured
    # facts) — populated only when `context.workspace` is a
    # TroubleshootWorkspaceContext. Internal/plumbing only: never
    # surfaced through any API response, never passed to the AI
    # provider (that remains Stage 4D's job).
    troubleshoot_facts: TroubleshootDeterministicFacts | None = None


def _normalize(text: str) -> str:
    return " ".join(text.strip().casefold().split())


def _troubleshoot_payload_has_content(workspace: TroubleshootWorkspaceContext) -> bool:
    """Whether the employee has actually engaged with the structured
    Troubleshoot workspace at all, as opposed to a legacy-only attempt
    with no `workspace.payload` (or an entirely empty one) — an empty
    structured context has nothing for it to be authoritative *over*,
    so it's treated the same as "no structured payload" and the
    original legacy-blob check applies instead.
    """
    return bool(
        workspace.observations
        or workspace.evidence_reviewed
        or workspace.hypotheses
        or workspace.diagnosis.root_cause.strip()
        or workspace.diagnosis.confidence
        or workspace.resolution.proposed_fix.strip()
        or workspace.resolution.validation_plan
    )


def evaluate_deterministic(
    criteria: list[QuestEvaluationCriterion], context: EvaluationContext
) -> DeterministicEvaluationResult:
    """The only criteria checked deterministically are DETERMINISTIC-type
    criteria with a non-empty `expected_answer`, verified as an exact
    (normalized: trimmed, case-insensitive, whitespace-collapsed)
    substring match against the employee's combined submission text.
    This is intentionally NOT fuzzy matching — no similarity threshold,
    no partial credit for "close enough."

    BEHAVIORAL criteria have no safe deterministic link to a specific
    employee action in the current schema (no FK from criterion to
    task), and QUALITATIVE criteria are qualitative by definition — both
    are recorded as requiring qualitative (AI) evaluation rather than
    inventing a deterministic result for them.

    Phase 7 Stage 4B: takes the typed `EvaluationContext` instead of the
    raw submission dict.

    Phase 7 Stage 4C: for a TROUBLESHOOT-workspace attempt where a
    structured payload is actually present (`context.workspace` is a
    non-empty `TroubleshootWorkspaceContext` — see
    `_troubleshoot_payload_has_content`), the structured
    `diagnosis.root_cause` field is **authoritative**: a DETERMINISTIC
    criterion's `expected_answer` is checked only against it, not
    against the legacy blob. The legacy fields remain compatibility
    data — they can never rescue an incorrect structured answer, and
    (symmetrically) they can never fail a correct one either. This was
    corrected from an initial additive OR design specifically because
    OR-matching let a client independently PATCH the legacy `reasoning`
    field with the expected text while the actual structured diagnosis
    stayed wrong, producing a false objective pass — an evaluation
    integrity gap, not a compatibility feature.

    The legacy-blob check still runs, unconditionally, for two cases
    only: GENERAL-workspace attempts (`context.workspace` carries no
    `diagnosis` field at all), and TROUBLESHOOT attempts with **no**
    structured payload at all (legacy-only, e.g. pre-Stage-3 data) —
    both preserved exactly as before this correction.

    This function still does not read `hypotheses`, `observations`,
    `evidence_reviewed`, `diagnosis.confidence`, or `resolution` —
    those remain outside deterministic scoring in this stage (Stage 4C
    spec §11/§13/§14/§16: activity and self-reported confidence are
    never objective correctness; evidence-selection and hypothesis
    quality have no safe deterministic representation in the current
    schema and are deferred).
    """
    deterministic = context.deterministic
    combined_text = _normalize(
        " ".join((deterministic.findings, deterministic.reasoning, deterministic.solution))
    )

    troubleshoot_workspace = (
        context.workspace if isinstance(context.workspace, TroubleshootWorkspaceContext) else None
    )
    structured_authoritative = troubleshoot_workspace is not None and _troubleshoot_payload_has_content(
        troubleshoot_workspace
    )
    normalized_root_cause = (
        _normalize(troubleshoot_workspace.diagnosis.root_cause) if troubleshoot_workspace else ""
    )
    root_cause_matched_a_criterion = False

    outcomes: list[DeterministicCriterionOutcome] = []
    qualitative_descriptions: list[str] = []

    for criterion in criteria:
        expected = (criterion.expected_answer or "").strip()
        if criterion.criterion_type == "DETERMINISTIC" and expected:
            normalized_expected = _normalize(expected)
            if structured_authoritative:
                # The structured field is the only source of truth once
                # a structured payload exists — the legacy blob is
                # deliberately not consulted here at all.
                passed = normalized_expected in normalized_root_cause
                matched_root_cause = passed
            else:
                # GENERAL, or a legacy-only TROUBLESHOOT attempt — the
                # original, unmodified legacy-blob check.
                passed = normalized_expected in combined_text
                matched_root_cause = False
            if matched_root_cause:
                root_cause_matched_a_criterion = True
            outcomes.append(
                DeterministicCriterionOutcome(
                    criterion_id=criterion.id,
                    criterion_type=criterion.criterion_type,
                    name=criterion.name,
                    passed=passed,
                    score=float(criterion.max_score) if passed else 0.0,
                    max_score=float(criterion.max_score),
                    evidence="Checked whether the expected answer appears in the employee's "
                    "submission (exact match, case-insensitive).",
                )
            )
        else:
            outcomes.append(
                DeterministicCriterionOutcome(
                    criterion_id=criterion.id,
                    criterion_type=criterion.criterion_type,
                    name=criterion.name,
                    passed=None,
                    score=0.0,
                    max_score=float(criterion.max_score),
                    evidence="Requires qualitative evaluation; not deterministically checkable "
                    "from the current submission schema.",
                )
            )
            qualitative_descriptions.append(
                f"{criterion.name}: {criterion.description}" if criterion.description else criterion.name
            )

    checkable = [o for o in outcomes if o.passed is not None]
    if checkable:
        total_max = sum(o.max_score for o in checkable)
        total_score = sum(o.score for o in checkable)
        objective_score = round(100 * total_score / total_max, 1) if total_max > 0 else 100.0
        objective_passed = all(o.passed for o in checkable)
    else:
        # Nothing was deterministically checkable — absence of a
        # checkable criterion is not evidence of failure, same principle
        # as CapabilityProfile's NOT_OBSERVED.
        objective_score = 100.0
        objective_passed = True

    troubleshoot_facts = None
    if troubleshoot_workspace is not None:
        deterministic_criteria_exist = any(
            c.criterion_type == "DETERMINISTIC" and (c.expected_answer or "").strip() for c in criteria
        )
        troubleshoot_facts = TroubleshootDeterministicFacts(
            root_cause_present=bool(troubleshoot_workspace.diagnosis.root_cause.strip()),
            proposed_fix_present=bool(troubleshoot_workspace.resolution.proposed_fix.strip()),
            root_cause_matches_expected=(
                root_cause_matched_a_criterion if deterministic_criteria_exist else None
            ),
        )

    return DeterministicEvaluationResult(
        criterion_outcomes=outcomes,
        objective_passed=objective_passed,
        objective_score=objective_score,
        qualitative_criterion_descriptions=qualitative_descriptions,
        troubleshoot_facts=troubleshoot_facts,
    )


def _deterministic_strength(det_result: DeterministicEvaluationResult) -> str:
    checkable = [o for o in det_result.criterion_outcomes if o.passed is not None]
    if not checkable:
        return "CAPABLE"
    if all(o.passed for o in checkable):
        return "STRONG" if len(checkable) >= 2 else "CAPABLE"
    return "DEVELOPING"


# =====================================================================
# Persistence helpers
# =====================================================================


async def get_evaluation_for_quest_attempt(
    db: AsyncSession, quest_attempt_id: str
) -> CapabilityEvaluation | None:
    stmt = select(CapabilityEvaluation).where(CapabilityEvaluation.quest_attempt_id == quest_attempt_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _create_deterministic_quest_evidence(
    db: AsyncSession,
    employee: Employee,
    attempt: QuestAttempt,
    quest: Quest,
    det_result: DeterministicEvaluationResult,
    capability_mappings: list,
) -> list[CapabilityEvidence]:
    """One evidence row per capability the manager mapped to this quest —
    never a fabricated mapping. `evaluation_id` is left unset here
    (mirrors Mission's capability_evidence_pipeline.py: deterministic
    evidence is never tied to an AI evaluation record, only AI-sourced
    rows are)."""
    if not capability_mappings:
        return []

    strength = _deterministic_strength(det_result)
    checkable = [o for o in det_result.criterion_outcomes if o.passed is not None]
    if checkable:
        passed_count = sum(1 for o in checkable if o.passed)
        observation = (
            f'Completed "{quest.title}" and satisfied {passed_count}/{len(checkable)} '
            "objectively-checkable evaluation criteria."
        )
    else:
        observation = f'Completed "{quest.title}", including all required tasks.'

    created: list[CapabilityEvidence] = []
    for mapping in capability_mappings:
        row = await capability_service.create_evidence(
            db,
            employee_id=employee.id,
            quest_attempt_id=attempt.id,
            capability_id=mapping.capability_id,
            evidence_type=DETERMINISTIC_EVIDENCE_TYPE,
            observation=observation,
            strength=strength,
            confidence=0.6,
            source="deterministic",
        )
        created.append(row)
    return created


async def _create_quest_ai_evidence(
    db: AsyncSession,
    employee: Employee,
    attempt: QuestAttempt,
    evaluation: CapabilityEvaluation,
    validated: AIEvaluationResponse,
) -> list[CapabilityEvidence]:
    created: list[CapabilityEvidence] = []
    for assessment in validated.capabilities:
        capability = await capability_service.get_capability_by_key(db, assessment.capability)
        if capability is None:
            continue  # defensive; schema validation already guarantees a known key
        row = await capability_service.create_evidence(
            db,
            employee_id=employee.id,
            quest_attempt_id=attempt.id,
            capability_id=capability.id,
            evidence_type="ai_interpretation",
            observation=assessment.evidence,
            strength=assessment.level,
            confidence=assessment.confidence,
            source="ai",
            evaluation_id=evaluation.id,
        )
        created.append(row)
    return created


def _build_quest_context(
    employee: Employee,
    quest: Quest,
    eval_context: EvaluationContext,
    det_result: DeterministicEvaluationResult,
    target_capability_keys: list[str],
) -> QuestAIEvaluationContext:
    """Phase 7 Stage 4B: reads `task_titles_completed/skipped` and
    `findings/reasoning/solution` from `eval_context.deterministic`/
    `eval_context.ai` instead of re-deriving them from `attempt.submission`
    a second time.

    Phase 7 Stage 4D: also passes `eval_context.workspace` through as
    `QuestAIEvaluationContext.troubleshoot` — but only when it's a
    `TroubleshootWorkspaceContext` that actually has content
    (`_troubleshoot_payload_has_content`, the same test Stage 4C's
    authority correction uses). GENERAL's `eval_context.workspace` is a
    `GeneralWorkspaceContext`, which maps to `None` here; a legacy-only
    TROUBLESHOOT attempt's `TroubleshootWorkspaceContext` is present but
    empty, which also maps to `None` — both preserve the exact
    pre-Stage-4D AI behavior (the "legacy compatibility" case Stage 4C
    established must keep working unchanged, now extended to the AI
    layer too). Nothing else about this function's output changed from
    Stage 4B — every other field is identical to before.
    """
    deterministic_results = [
        QuestDeterministicCriterionResult(name=o.name, passed=bool(o.passed), evidence=o.evidence)
        for o in det_result.criterion_outcomes
        if o.passed is not None
    ]

    troubleshoot_ai_context = None
    if isinstance(eval_context.workspace, TroubleshootWorkspaceContext) and _troubleshoot_payload_has_content(
        eval_context.workspace
    ):
        troubleshoot_ai_context = eval_context.workspace

    return QuestAIEvaluationContext(
        employee_job_title=employee.job_title,
        quest_title=quest.title,
        quest_description=quest.description or "",
        quest_type=quest.quest_type,
        task_titles_completed=eval_context.deterministic.task_titles_completed,
        task_titles_skipped=eval_context.deterministic.task_titles_skipped,
        findings=eval_context.ai.findings,
        reasoning=eval_context.ai.reasoning,
        solution=eval_context.ai.solution,
        deterministic_results=deterministic_results,
        qualitative_criterion_descriptions=det_result.qualitative_criterion_descriptions,
        target_capability_keys=target_capability_keys,
        troubleshoot=troubleshoot_ai_context,
        objective_passed=det_result.objective_passed,
        objective_score=det_result.objective_score,
    )


# =====================================================================
# Orchestrator
# =====================================================================


async def evaluate_attempt(
    db: AsyncSession, employee: Employee, quest: Quest, attempt: QuestAttempt
) -> CapabilityEvaluation | None:
    """Idempotent and concurrency-safe, mirroring
    ai_evaluation_service.evaluate_attempt's established pattern exactly.

    Returns the CapabilityEvaluation, or None if the quest has no
    QuestCapability mappings at all (deterministic-only completion — see
    NoCapabilityMappingError's docstring). On any AI failure, the
    attempt is returned to SUBMITTED and the exception re-raised; the
    employee's submitted work is never touched.
    """
    # Phase 8D: captured once, up front — exactly like attempt_id below,
    # since a rollback anywhere in this function (the IntegrityError-race
    # branch in particular) expires every attribute on every object this
    # session tracks, `employee` included. Re-accessing `employee.id`
    # after such a rollback would trigger an implicit lazy-load outside
    # an awaited context and blow up with MissingGreenlet — the same
    # class of bug this function's own comments already document for
    # `attempt.id`. Every readiness_service.check_and_trigger call below
    # uses this captured value, never a fresh `employee.id` access.
    employee_id = employee.id

    if attempt.status == "COMPLETED":
        existing = await get_evaluation_for_quest_attempt(db, attempt.id)
        # Safe and idempotent to call on every re-observation of a
        # COMPLETED attempt, not just the first — see readiness_service's
        # module docstring for why repeated calls never duplicate work.
        await readiness_service.check_and_trigger(employee_id)
        return existing  # None here means it completed via the no-mapping path — not an error to re-fetch

    if attempt.status not in ACTIVE_STATUSES:
        raise QuestAttemptNotEvaluableError(
            f"Cannot evaluate a quest attempt in status {attempt.status!r}"
        )

    # Partial-failure recovery, same shape as Mission's: an evaluation row
    # may already exist even though status reverted to SUBMITTED after a
    # prior crash between committing it and finishing evidence creation.
    existing = await get_evaluation_for_quest_attempt(db, attempt.id)
    if existing:
        existing_evidence = await capability_service.list_evidence_for_attempt(
            db, quest_attempt_id=attempt.id
        )
        if not any(e.evaluation_id == existing.id for e in existing_evidence):
            validated = AIEvaluationResponse.model_validate(existing.structured_result)
            new_evidence = await _create_quest_ai_evidence(db, employee, attempt, existing, validated)
            await capability_aggregation.recompute_profiles_for_evidence(db, employee.id, new_evidence)
        if attempt.status != "COMPLETED":
            attempt.status = "COMPLETED"
            await db.commit()
            await db.refresh(attempt)
        # Phase 8D: after the commit above, never before/instead of it.
        await readiness_service.check_and_trigger(employee_id)
        return existing

    # Mark EVALUATING before any slow/failable work, so a concurrent GET
    # sees the in-progress state (the frontend shows "Buddy is reviewing
    # your work" while this is true).
    if attempt.status != "EVALUATING":
        attempt.status = "EVALUATING"
        await db.commit()
        await db.refresh(attempt)

    quest_tasks = await quest_task_service.list_tasks(db, quest.id)
    criteria = await quest_evaluation_criterion_service.list_criteria(db, quest.id)
    capability_mappings = await quest_capability_service.list_mappings(db, quest.id)

    # Phase 7 Stage 4B: obtained once, before any of the existing
    # deterministic/AI work below — the single point where workspace_type
    # gets resolved to a typed WorkspaceContext (workspace_evaluation_registry.py).
    # Nothing past this line branches on workspace_type again.
    eval_context = build_evaluation_context(
        employee_id=employee.id,
        quest_id=quest.id,
        quest_type=quest.quest_type,
        workspace_type=quest.workspace_type,
        attempt_id=attempt.id,
        submission=attempt.submission or {},
        quest_tasks=quest_tasks,
    )

    det_result = evaluate_deterministic(criteria, eval_context)
    target_capability_keys = [m.capability.key for m in capability_mappings]

    if not target_capability_keys:
        # Nothing to interpret — the manager never mapped this quest to
        # any capability. Complete deterministically; there is no
        # honest AI capability claim to fabricate.
        attempt.status = "COMPLETED"
        attempt.score = det_result.objective_score
        attempt.passed = det_result.objective_passed
        await db.commit()
        await db.refresh(attempt)
        # Phase 8D: after the commit above, never before/instead of it.
        await readiness_service.check_and_trigger(employee_id)
        return None

    settings = get_settings()
    provider = get_ai_provider(settings.ai_provider)
    quest_ai_context = _build_quest_context(employee, quest, eval_context, det_result, target_capability_keys)

    try:
        # AIProviderError (unavailable/timeout) bubbles up as-is; the
        # `except` block below returns the attempt to SUBMITTED before
        # re-raising, so the API layer can map it to a recoverable
        # "still analyzing" state without losing anything.
        raw_response = await provider.generate_for_quest(quest_ai_context)

        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise AIEvaluationRejected(f"AI response was not valid JSON: {exc}") from exc

        try:
            validated = AIEvaluationResponse.model_validate(parsed)
        except ValidationError as exc:
            raise AIEvaluationRejected(f"AI response failed schema validation: {exc}") from exc

        evaluation = CapabilityEvaluation(
            quest_attempt_id=attempt.id,
            employee_id=employee.id,
            model=provider.model_name,
            prompt_version=settings.ai_prompt_version,
            evaluation_version=settings.ai_evaluation_version,
            raw_response=raw_response,
            structured_result=validated.model_dump(),
        )
        # Captured before the commit attempt: a rollback expires every
        # attribute on `attempt`, so touching attempt.id afterward would
        # trigger an implicit lazy-load outside an awaited context and
        # blow up with a MissingGreenlet error (same guard as Mission's).
        attempt_id = attempt.id

        db.add(evaluation)
        try:
            await db.commit()
        except IntegrityError:
            # Lost a race with a concurrent evaluate call for the same
            # attempt.
            await db.rollback()
            # `attempt`'s attributes are expired by the rollback — refresh
            # before touching any of them, or a plain read/write triggers
            # an implicit lazy-load outside an awaited context and blows
            # up with MissingGreenlet (same class of bug fixed in Phase
            # 3A's ai_evaluation_service.py).
            await db.refresh(attempt)
            existing = await get_evaluation_for_quest_attempt(db, attempt_id)
            if existing:
                if attempt.status != "COMPLETED":
                    attempt.status = "COMPLETED"
                    await db.commit()
                # Phase 8D: after the commit above, never before/instead of it.
                await readiness_service.check_and_trigger(employee_id)
                return existing
            raise
        await db.refresh(evaluation)

        det_evidence = await _create_deterministic_quest_evidence(
            db, employee, attempt, quest, det_result, capability_mappings
        )
        ai_evidence = await _create_quest_ai_evidence(db, employee, attempt, evaluation, validated)
        await capability_aggregation.recompute_profiles_for_evidence(
            db, employee.id, det_evidence + ai_evidence
        )

        attempt.status = "COMPLETED"
        attempt.score = det_result.objective_score
        attempt.passed = det_result.objective_passed
        attempt.completed_at = attempt.completed_at or datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(attempt)

        # Phase 8D: after the commit above, never before/instead of it —
        # this is the authoritative "Quest completion is durably
        # committed" point for the main success path.
        await readiness_service.check_and_trigger(employee_id)

        return evaluation

    except (AIProviderError, AIEvaluationRejected):
        await db.rollback()
        # Same MissingGreenlet guard as above: refresh before writing.
        await db.refresh(attempt)
        attempt.status = "SUBMITTED"
        await db.commit()
        raise

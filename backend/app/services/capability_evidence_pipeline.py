"""Deterministic evidence extraction — the first link in the capability
intelligence chain (MissionAttempt -> Evidence -> Evaluation -> Profile).

Runs only when a mission attempt genuinely passes (called from
mission_attempt_service.submit_attempt). A failed/incomplete attempt
creates nothing here, so absence of evidence is never mistaken for
negative evidence — NOT_OBSERVED means "hasn't happened yet," not "did
this badly."

The mapping below is the single, documented source of truth for which
deterministic facts support which capabilities. It's intentionally
conservative: a fact only maps to a capability where the link is direct
and explainable (mirrors the worked example in the Phase 3A spec —
correctly identifying the affected service supports technical_
understanding/troubleshooting, never communication). communication and
documentation only get a weak *base* signal here (did the employee
explain themselves at all) — reading the actual *quality* of that
explanation is the AI's job (capability_evidence_pipeline_ai / Stage 7),
not this deterministic layer's.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CapabilityEvidence, MissionAttempt
from app.services import capability_service
from app.services.mission_quizzes import QuizGradeResult
from app.services.mission_scenarios import GradeResult

# evidence_type -> [(capability_key, base_confidence), ...]
DETERMINISTIC_EVIDENCE_RULES: dict[str, list[tuple[str, float]]] = {
    "correct_service_selection": [
        ("troubleshooting", 0.6),
        ("technical_understanding", 0.5),
    ],
    "correct_root_cause": [
        ("troubleshooting", 0.75),
        ("problem_solving", 0.65),
        ("technical_understanding", 0.5),
    ],
    "required_evidence_viewed": [
        ("independence", 0.55),
        ("troubleshooting", 0.45),
    ],
    "reasoning_provided": [
        ("documentation", 0.4),
        ("communication", 0.35),
    ],
    "mission_completed": [
        ("independence", 0.5),
        ("problem_solving", 0.5),
    ],
    # A passed quiz is evidence the employee actually retained the
    # material, not just that they clicked through it — supports the
    # same two capabilities a correct investigation conclusion does,
    # at a lower base confidence since a multiple-choice pass is a
    # weaker signal than diagnosing a live scenario correctly.
    "quiz_passed": [
        ("technical_understanding", 0.5),
        ("documentation", 0.35),
    ],
}

# A deterministic, non-judgmental proxy for "did they write a real
# explanation" — presence only, never a quality/grammar check. Quality is
# explicitly out of scope for the deterministic layer.
MIN_REASONING_LENGTH = 20


async def extract_deterministic_evidence(
    db: AsyncSession, attempt: MissionAttempt, result: GradeResult
) -> list[CapabilityEvidence]:
    """Idempotent: if deterministic evidence already exists for this
    attempt (e.g. this somehow got called twice), returns the existing
    rows instead of creating duplicates."""
    existing = await capability_service.list_evidence_for_attempt(db, attempt.id)
    existing_deterministic = [e for e in existing if e.source == "deterministic"]
    if existing_deterministic:
        return existing_deterministic

    facts: list[tuple[str, str]] = []  # (evidence_type, observation)

    if result.service_correct:
        facts.append(
            (
                "correct_service_selection",
                f"Correctly identified {attempt.affected_service} as the affected service.",
            )
        )
    if result.cause_correct:
        facts.append(
            (
                "correct_root_cause",
                f"Correctly traced the root cause: {attempt.likely_cause}.",
            )
        )
    if result.explored_widely:
        categories = ", ".join(sorted(result.evidence_categories_viewed))
        facts.append(
            (
                "required_evidence_viewed",
                f"Checked evidence across multiple sources ({categories}) before concluding.",
            )
        )
    if attempt.reasoning and len(attempt.reasoning.strip()) >= MIN_REASONING_LENGTH:
        facts.append(
            (
                "reasoning_provided",
                "Explained their reasoning in their own words before submitting.",
            )
        )
    # This function only ever runs on a pass (see submit_attempt), so
    # "mission_completed" is an unconditional fact here.
    facts.append(
        (
            "mission_completed",
            "Completed the investigation end-to-end and reached the correct conclusion.",
        )
    )

    # A correct conclusion reached after genuinely exploring the evidence
    # is stronger proof of capability than the same conclusion reached by
    # a narrow guess — one documented, uniform rule, not per-fact tuning.
    strength = "STRONG" if result.explored_widely else "CAPABLE"

    return await _create_evidence_rows(db, attempt, facts, strength)


async def _create_evidence_rows(
    db: AsyncSession, attempt: MissionAttempt, facts: list[tuple[str, str]], strength: str
) -> list[CapabilityEvidence]:
    """Shared by every extract_*_evidence function below — one fact list
    in, evidence rows for every capability DETERMINISTIC_EVIDENCE_RULES
    maps that fact to, out."""
    created: list[CapabilityEvidence] = []
    for evidence_type, observation in facts:
        for capability_key, confidence in DETERMINISTIC_EVIDENCE_RULES.get(evidence_type, []):
            capability = await capability_service.get_capability_by_key(db, capability_key)
            if capability is None:
                # Defensive only — capabilities are seeded at startup, this
                # should never happen. Never let a missing lookup break
                # mission submission itself.
                continue
            row = await capability_service.create_evidence(
                db,
                employee_id=attempt.employee_id,
                mission_attempt_id=attempt.id,
                capability_id=capability.id,
                evidence_type=evidence_type,
                observation=observation,
                strength=strength,
                confidence=confidence,
                source="deterministic",
            )
            created.append(row)

    return created


async def extract_quiz_evidence(
    db: AsyncSession, attempt: MissionAttempt, result: QuizGradeResult
) -> list[CapabilityEvidence]:
    """Runs only on a passed quiz (every question answered correctly —
    see mission_quizzes.grade). Deliberately no AI step follows this one
    (see mission.py's `workspace_type` docstring), so this deterministic
    layer is the whole evidence story for a quiz mission, not just the
    first link in a longer chain."""
    existing = await capability_service.list_evidence_for_attempt(db, attempt.id)
    if any(e.source == "deterministic" for e in existing):
        return existing

    facts = [
        (
            "quiz_passed",
            f"Answered all {result.total} comprehension questions correctly.",
        ),
        (
            "mission_completed",
            "Completed the training/reading check end-to-end.",
        ),
    ]
    return await _create_evidence_rows(db, attempt, facts, strength="CAPABLE")


async def extract_reflection_evidence(db: AsyncSession, attempt: MissionAttempt) -> list[CapabilityEvidence]:
    """Runs only once a reflection submission has cleared the real-effort
    bar (see mission_attempt_service._grade_reflection) — the deterministic
    half of the same two-stage pattern investigation missions use
    (deterministic facts first, then the AI's qualitative read via
    ai_evaluation_service.evaluate_attempt on the same `reasoning` text)."""
    existing = await capability_service.list_evidence_for_attempt(db, attempt.id)
    if any(e.source == "deterministic" for e in existing):
        return existing

    facts = [
        (
            "reasoning_provided",
            "Described their work in their own words before submitting.",
        ),
        (
            "mission_completed",
            "Completed the mission end-to-end.",
        ),
    ]
    return await _create_evidence_rows(db, attempt, facts, strength="CAPABLE")

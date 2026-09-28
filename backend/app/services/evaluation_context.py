"""Phase 7 Stage 4B — the EvaluationContext contract.

Stage 4A identified exactly one gap in the existing evaluation pipeline:
`evaluate_deterministic` and `_build_quest_context` both read three fixed
keys (`findings`/`reasoning`/`solution`) off the raw `submission` dict and
nothing else — any richer, workspace-specific structure sitting in
`submission["workspace"]["payload"]` was invisible to them, even though
it was already being persisted correctly (Stage 3).

This module introduces the typed container that closes that gap without
touching what the evaluator actually *does* with the data. It is
plumbing only:

- `common` / `deterministic` / `ai` are populated identically to what
  `_build_quest_context` has always computed — same values, now typed
  instead of re-read from a dict at two different call sites.
- `workspace` is new: a workspace-specific, structurally typed view of
  `submission["workspace"]["payload"]`, produced by whichever builder
  `workspace_evaluation_registry.py` resolves for the quest's
  `workspace_type`. Nothing in this stage *reads* `workspace` for
  scoring or AI interpretation — it exists so Stage 4C/4D have
  somewhere real to read from, without the central evaluator ever
  needing to know what a TROUBLESHOOT payload looks like.

Every dataclass here is deliberately small and inert (no methods, no
validation logic) — construction happens in `build_evaluation_context`
and in `workspace_evaluation_registry.py`'s builders, never inside these
types themselves.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EvaluationCommonContext:
    """Identity — which quest, which attempt, which employee, which
    workspace_type. Never used to branch evaluation *logic*; only to
    resolve which workspace context builder ran (see
    workspace_evaluation_registry.py) and for evidence provenance."""

    quest_id: str
    attempt_id: str
    employee_id: str
    quest_type: str
    workspace_type: str


@dataclass
class EvaluationDeterministicContext:
    """Exactly what `evaluate_deterministic` and `_build_quest_context`
    have always read from `attempt.submission` — moved into a typed
    container, not changed in meaning, value, or source. Every
    workspace_type populates this identically: it's the compatibility
    surface the Stage 3 frontend adapter guarantees every submission
    provides (via `toSubmission`'s legacy-field synthesis), regardless
    of whether a richer `workspace` block also exists below.
    """

    findings: str
    reasoning: str
    solution: str
    completed_task_ids: set[str]
    task_titles_completed: list[str]
    task_titles_skipped: list[str]


@dataclass
class EvaluationAIContext:
    """What's available for AI evaluation. In Stage 4B this carries only
    the same flattened legacy strings `_build_quest_context` has always
    passed to `QuestAIEvaluationContext` — Stage 4D is where this gains
    structured workspace fields the AI provider can read directly.
    Nothing about what the AI provider actually receives changes in
    this stage; this only moves *where* that data is sourced from."""

    findings: str
    reasoning: str
    solution: str


@dataclass
class GeneralWorkspaceContext:
    """GENERAL — and any workspace_type without a registered builder —
    has no structured payload beyond the legacy fields already captured
    in `deterministic`/`ai` above. An explicit empty marker type, not
    `None`, so callers never need a null-check to treat
    `EvaluationContext.workspace` uniformly regardless of workspace_type."""


@dataclass
class TroubleshootHypothesisContext:
    """Mirrors the frontend's `Hypothesis` shape
    (troubleshootSubmissionAdapter.ts) exactly — same four fields, same
    meaning. `supporting_evidence_ids` is a structural fact (which ids
    the employee linked), not itself evidence of competence — see
    TroubleshootWorkspaceContext's docstring."""

    id: str
    statement: str
    reasoning: str
    supporting_evidence_ids: list[str]


@dataclass
class TroubleshootDiagnosisContext:
    root_cause: str
    # The employee's own stated read of their certainty. Never an
    # evaluation score, never capability evidence, never scoring input —
    # Stage 4A §10 and §11 are explicit about this, and this field
    # exists only so it *can* be shown as context; nothing in this
    # codebase may reinterpret it as anything else.
    confidence: str | None


@dataclass
class TroubleshootResolutionContext:
    proposed_fix: str
    validation_plan: str | None


@dataclass
class TroubleshootWorkspaceContext:
    """The structured Troubleshoot payload, reconstructed server-side
    from `submission["workspace"]["payload"]`.

    `evidence_reviewed` is a structural fact (which evidence ids were
    marked reviewed) — per Stage 4A's explicit boundary, this must never
    by itself become "the employee demonstrated troubleshooting
    capability." It is made available here as *context*; whether and how
    it should inform anything is a Stage 4C decision, not one this
    context type makes for its caller.
    """

    observations: list[str]
    evidence_reviewed: list[str]
    hypotheses: list[TroubleshootHypothesisContext]
    diagnosis: TroubleshootDiagnosisContext
    resolution: TroubleshootResolutionContext


WorkspaceContext = GeneralWorkspaceContext | TroubleshootWorkspaceContext


@dataclass
class EvaluationContext:
    """The full contract `evaluate_attempt` obtains once per evaluation,
    before doing any of its existing deterministic/AI work. Nothing
    downstream of this type's construction needs to know which
    workspace_type produced `workspace` — it's already resolved into a
    concrete Python type (`GeneralWorkspaceContext` or
    `TroubleshootWorkspaceContext` today) by the time this object exists.

    Deliberately excludes anything from `QuestEvaluationCriterion`
    (`expected_answer`/`expected_behavior`/`reference_solution`/
    `max_score`) — there is no field on this type, or any type it is
    built from, capable of holding hidden evaluation data. Deterministic
    matching against those hidden fields still happens exactly where it
    always has (`evaluate_deterministic`, given the *criteria* directly,
    never through this context).
    """

    common: EvaluationCommonContext
    deterministic: EvaluationDeterministicContext
    workspace: WorkspaceContext
    ai: EvaluationAIContext


def build_evaluation_context(
    *,
    employee_id: str,
    quest_id: str,
    quest_type: str,
    workspace_type: str,
    attempt_id: str,
    submission: dict,
    quest_tasks: list,
) -> EvaluationContext:
    """The shared assembly step every workspace_type goes through
    identically for `common`/`deterministic`/`ai` — only `workspace`
    varies, and only via `workspace_evaluation_registry.resolve_workspace_context_builder`,
    imported lazily below to avoid a circular import (the registry
    module imports the dataclasses from this one).
    """
    from app.services.workspace_evaluation_registry import resolve_workspace_context_builder

    completed_ids = set(submission.get("completed_task_ids") or [])
    completed_titles = [t.title for t in quest_tasks if t.id in completed_ids]
    skipped_titles = [t.title for t in quest_tasks if t.id not in completed_ids and not t.required]

    findings = str(submission.get("findings") or "")
    reasoning = str(submission.get("reasoning") or "")
    solution = str(submission.get("solution") or "")

    builder = resolve_workspace_context_builder(workspace_type)
    workspace_context = builder(submission)

    return EvaluationContext(
        common=EvaluationCommonContext(
            quest_id=quest_id,
            attempt_id=attempt_id,
            employee_id=employee_id,
            quest_type=quest_type,
            workspace_type=workspace_type,
        ),
        deterministic=EvaluationDeterministicContext(
            findings=findings,
            reasoning=reasoning,
            solution=solution,
            completed_task_ids=completed_ids,
            task_titles_completed=completed_titles,
            task_titles_skipped=skipped_titles,
        ),
        workspace=workspace_context,
        ai=EvaluationAIContext(findings=findings, reasoning=reasoning, solution=solution),
    )

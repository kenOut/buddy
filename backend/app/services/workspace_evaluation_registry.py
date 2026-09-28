"""Phase 7 Stage 4B — the backend's workspace evaluation context
registry.

This is the direct backend mirror of the frontend's
`resolveWorkspace.ts` (Stage 1): a thin lookup keyed by the same
`workspace_type` values the Quest model already validates against
(`WORKSPACE_TYPES`), resolving to a builder function that turns a raw
`submission` dict into a typed `WorkspaceContext`. Nothing here is a
second evaluation pipeline — a builder's only job is parsing, and
`evaluate_attempt` (quest_evaluation_service.py) never branches on
workspace_type itself; it just calls whatever builder this module
hands back.

Adding a future workspace type (INVESTIGATION/DESIGN/BUILD/ANALYSIS/
FIX) means adding one entry here — nothing about `EvaluationContext`,
`evaluate_attempt`, or any other registered builder changes.
"""

from collections.abc import Callable

from app.services.evaluation_context import (
    GeneralWorkspaceContext,
    TroubleshootDiagnosisContext,
    TroubleshootHypothesisContext,
    TroubleshootResolutionContext,
    TroubleshootWorkspaceContext,
    WorkspaceContext,
)

WorkspaceContextBuilder = Callable[[dict], WorkspaceContext]


def _build_general_context(submission: dict) -> WorkspaceContext:
    return GeneralWorkspaceContext()


# ---------------------------------------------------------------------
# TROUBLESHOOT — defensive parsing, mirrors the field-by-field coercion
# discipline of troubleshootSubmissionAdapter.ts's fromSubmission()
# exactly (same "never crash, default per field independently" rule).
# This is the backend's OWN reconstruction of the persisted JSON, not a
# call into frontend code — the two stay in sync because they both
# read/write the same wire shape (`submission.workspace.payload`), not
# because they share an algorithm. Per Stage 4B's explicit instruction,
# the backend is authoritative; this function never trusts a frontend
# conclusion, only the raw persisted data.
# ---------------------------------------------------------------------


def _as_str(value: object) -> str:
    return value if isinstance(value, str) else ""


def _as_nullable_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, str)]


def _build_hypothesis_context(value: object, fallback_index: int) -> TroubleshootHypothesisContext | None:
    """Returns None for an entry that's malformed or entirely empty —
    dropped, not fatal, exactly like the frontend adapter's own
    `asHypothesis`."""
    if not isinstance(value, dict):
        return None
    statement = _as_str(value.get("statement"))
    reasoning = _as_str(value.get("reasoning"))
    supporting = _as_str_list(value.get("supporting_evidence_ids"))
    if not statement and not reasoning and not supporting:
        return None
    hyp_id = value.get("id")
    return TroubleshootHypothesisContext(
        id=hyp_id if isinstance(hyp_id, str) and hyp_id else f"restored-{fallback_index}",
        statement=statement,
        reasoning=reasoning,
        supporting_evidence_ids=supporting,
    )


def _build_hypotheses(value: object) -> list[TroubleshootHypothesisContext]:
    if not isinstance(value, list):
        return []
    hypotheses: list[TroubleshootHypothesisContext] = []
    for i, item in enumerate(value):
        hypothesis = _build_hypothesis_context(item, i)
        if hypothesis is not None:
            hypotheses.append(hypothesis)
    return hypotheses


def _build_diagnosis_context(value: object) -> TroubleshootDiagnosisContext:
    if not isinstance(value, dict):
        return TroubleshootDiagnosisContext(root_cause="", confidence=None)
    return TroubleshootDiagnosisContext(
        root_cause=_as_str(value.get("root_cause")),
        confidence=_as_nullable_str(value.get("confidence")),
    )


def _build_resolution_context(value: object) -> TroubleshootResolutionContext:
    if not isinstance(value, dict):
        return TroubleshootResolutionContext(proposed_fix="", validation_plan=None)
    return TroubleshootResolutionContext(
        proposed_fix=_as_str(value.get("proposed_fix")),
        validation_plan=_as_nullable_str(value.get("validation_plan")),
    )


def _build_troubleshoot_context(submission: dict) -> WorkspaceContext:
    """Handles every case Stage 3/4B called out, none of them by
    crashing: missing `workspace` key (legacy attempt), `workspace` set
    but `payload` missing/null, a partial payload (some fields absent),
    and a payload where a field holds the wrong type entirely (string,
    number, array where an object was expected, etc.) — every field
    below defaults independently rather than the whole function
    bailing out on the first surprise."""
    workspace = submission.get("workspace")
    payload = workspace.get("payload") if isinstance(workspace, dict) else None
    if not isinstance(payload, dict):
        payload = {}

    return TroubleshootWorkspaceContext(
        observations=_as_str_list(payload.get("observations")),
        evidence_reviewed=_as_str_list(payload.get("evidence_reviewed")),
        hypotheses=_build_hypotheses(payload.get("hypotheses")),
        diagnosis=_build_diagnosis_context(payload.get("diagnosis")),
        resolution=_build_resolution_context(payload.get("resolution")),
    )


_WORKSPACE_CONTEXT_BUILDERS: dict[str, WorkspaceContextBuilder] = {
    "TROUBLESHOOT": _build_troubleshoot_context,
}

_FALLBACK_BUILDER: WorkspaceContextBuilder = _build_general_context


def resolve_workspace_context_builder(workspace_type: str) -> WorkspaceContextBuilder:
    """Unregistered workspace_type values — including `GENERAL` itself,
    and any future type not yet given its own builder — fall back to
    the empty `GeneralWorkspaceContext` builder. Never raises: an
    unknown workspace_type must not take down evaluation, mirroring
    `resolveWorkspace.ts`'s exact fallback discipline on the frontend.
    """
    return _WORKSPACE_CONTEXT_BUILDERS.get(workspace_type, _FALLBACK_BUILDER)

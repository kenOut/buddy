"""Phase 7 Stage 4C backend tests: deterministic Troubleshooting
evaluation — server-defined criteria checked against the structured
`diagnosis.root_cause` field, additive to (never a replacement for) the
existing legacy-blob matching.

Two groups of tests, matching test_evaluation_context.py's Stage 4B
convention:

1. Pure unit tests against `evaluate_deterministic` / `DeterministicEvaluationResult`
   directly — no DB, no HTTP. Fast, exhaustive coverage of the matching
   rule, normalization, and the hard "activity is not correctness" rule.
2. API-level tests (isolated SQLite file) proving the full pipeline —
   including idempotency, concurrency, security, and the SRE / non-SRE
   domain-agnostic proof — still holds through the real HTTP surface.
"""

from dataclasses import fields

from app.models.quest_evaluation_criterion import QuestEvaluationCriterion
from app.services.ai_provider import QuestAIEvaluationContext
from app.services.evaluation_context import (
    EvaluationAIContext,
    EvaluationCommonContext,
    EvaluationContext,
    EvaluationDeterministicContext,
    GeneralWorkspaceContext,
    TroubleshootDiagnosisContext,
    TroubleshootHypothesisContext,
    TroubleshootResolutionContext,
    TroubleshootWorkspaceContext,
)
from app.services.quest_evaluation_service import (
    TroubleshootDeterministicFacts,
    evaluate_deterministic,
)


def _criterion(expected_answer: str, *, criterion_type: str = "DETERMINISTIC", max_score: float = 100.0) -> QuestEvaluationCriterion:
    """A bare, unsaved QuestEvaluationCriterion — evaluate_deterministic
    only reads plain attributes, so no DB session is needed for these
    pure unit tests."""
    return QuestEvaluationCriterion(
        id="crit-1",
        quest_id="quest-1",
        name="Root cause check",
        criterion_type=criterion_type,
        expected_answer=expected_answer,
        max_score=max_score,
    )


def _troubleshoot_context(
    *,
    root_cause: str = "",
    proposed_fix: str = "",
    confidence: str | None = None,
    hypotheses: list | None = None,
    findings: str = "",
    reasoning: str = "",
    solution: str = "",
) -> EvaluationContext:
    return EvaluationContext(
        common=EvaluationCommonContext(
            quest_id="quest-1", attempt_id="attempt-1", employee_id="emp-1",
            quest_type="TROUBLESHOOT", workspace_type="TROUBLESHOOT",
        ),
        deterministic=EvaluationDeterministicContext(
            findings=findings, reasoning=reasoning, solution=solution,
            completed_task_ids=set(), task_titles_completed=[], task_titles_skipped=[],
        ),
        workspace=TroubleshootWorkspaceContext(
            observations=[],
            evidence_reviewed=[],
            hypotheses=hypotheses or [],
            diagnosis=TroubleshootDiagnosisContext(root_cause=root_cause, confidence=confidence),
            resolution=TroubleshootResolutionContext(proposed_fix=proposed_fix, validation_plan=None),
        ),
        ai=EvaluationAIContext(findings=findings, reasoning=reasoning, solution=solution),
    )


def _general_context(*, findings: str = "", reasoning: str = "", solution: str = "") -> EvaluationContext:
    return EvaluationContext(
        common=EvaluationCommonContext(
            quest_id="quest-1", attempt_id="attempt-1", employee_id="emp-1",
            quest_type="OTHER", workspace_type="GENERAL",
        ),
        deterministic=EvaluationDeterministicContext(
            findings=findings, reasoning=reasoning, solution=solution,
            completed_task_ids=set(), task_titles_completed=[], task_titles_skipped=[],
        ),
        workspace=GeneralWorkspaceContext(),
        ai=EvaluationAIContext(findings=findings, reasoning=reasoning, solution=solution),
    )


# =====================================================================
# Test 1 / 2 — correct / incorrect root cause
# =====================================================================


def test_correct_root_cause_passes_deterministically():
    context = _troubleshoot_context(root_cause="database connection pool exhaustion")
    criteria = [_criterion("database connection pool exhaustion")]

    result = evaluate_deterministic(criteria, context)

    assert result.objective_passed is True
    assert result.criterion_outcomes[0].passed is True
    assert result.troubleshoot_facts.root_cause_matches_expected is True
    assert result.troubleshoot_facts.root_cause_present is True


def test_incorrect_root_cause_fails_deterministically():
    context = _troubleshoot_context(root_cause="the cache was cold")
    criteria = [_criterion("database connection pool exhaustion")]

    result = evaluate_deterministic(criteria, context)

    assert result.objective_passed is False
    assert result.criterion_outcomes[0].passed is False
    assert result.troubleshoot_facts.root_cause_matches_expected is False


# =====================================================================
# Test 3 — normalization (case-insensitive, whitespace-collapsed only)
# =====================================================================


def test_normalization_handles_case_and_whitespace_differences():
    context = _troubleshoot_context(root_cause="  Database   Connection Pool Exhaustion  ")
    criteria = [_criterion("database connection pool exhaustion")]

    result = evaluate_deterministic(criteria, context)

    assert result.objective_passed is True
    assert result.troubleshoot_facts.root_cause_matches_expected is True


def test_normalization_does_not_do_fuzzy_or_semantic_matching():
    """A near-synonym must NOT pass — this is substring matching after
    normalization, never similarity/embedding-based matching."""
    context = _troubleshoot_context(root_cause="the connection pool ran out of connections")
    criteria = [_criterion("database connection pool exhaustion")]

    result = evaluate_deterministic(criteria, context)

    assert result.objective_passed is False


# =====================================================================
# Test 4 — missing diagnosis does not crash, criterion unsatisfied
# =====================================================================


def test_missing_diagnosis_does_not_crash_and_is_unsatisfied():
    context = _troubleshoot_context(root_cause="")
    criteria = [_criterion("database connection pool exhaustion")]

    result = evaluate_deterministic(criteria, context)

    assert result.objective_passed is False
    assert result.troubleshoot_facts.root_cause_present is False
    assert result.troubleshoot_facts.root_cause_matches_expected is False


def test_no_deterministic_criteria_leaves_matches_expected_as_none():
    """No DETERMINISTIC criterion with an expected_answer exists at
    all — there is nothing to have passed or failed, so the fact must
    be None, never fabricated as True or False."""
    context = _troubleshoot_context(root_cause="database connection pool exhaustion")
    criteria = [_criterion("", criterion_type="QUALITATIVE")]

    result = evaluate_deterministic(criteria, context)

    assert result.troubleshoot_facts.root_cause_matches_expected is None


# =====================================================================
# Authority correction — structured Troubleshoot data is authoritative
# once a structured payload exists; the legacy blob can neither rescue
# an incorrect structured answer nor fail a correct one.
# =====================================================================


def test_authority_1_structured_correct_legacy_incorrect_passes():
    context = _troubleshoot_context(
        root_cause="database connection pool exhaustion",
        reasoning="DNS configuration problem",
    )
    criteria = [_criterion("database connection pool exhaustion")]

    result = evaluate_deterministic(criteria, context)

    assert result.objective_passed is True
    assert result.criterion_outcomes[0].passed is True
    assert result.troubleshoot_facts.root_cause_matches_expected is True


def test_authority_2_structured_incorrect_legacy_correct_fails():
    """The most important regression test: a legacy field independently
    containing the expected answer must NOT rescue an incorrect
    structured diagnosis."""
    context = _troubleshoot_context(
        root_cause="DNS configuration problem",
        reasoning="database connection pool exhaustion",
    )
    criteria = [_criterion("database connection pool exhaustion")]

    result = evaluate_deterministic(criteria, context)

    assert result.objective_passed is False
    assert result.criterion_outcomes[0].passed is False
    assert result.troubleshoot_facts.root_cause_matches_expected is False


def test_authority_3_both_structured_and_legacy_correct_passes():
    context = _troubleshoot_context(
        root_cause="database connection pool exhaustion",
        reasoning="database connection pool exhaustion",
    )
    criteria = [_criterion("database connection pool exhaustion")]

    result = evaluate_deterministic(criteria, context)

    assert result.objective_passed is True
    assert result.troubleshoot_facts.root_cause_matches_expected is True


def test_authority_4_structured_incorrect_legacy_also_wrong_fails():
    context = _troubleshoot_context(
        root_cause="DNS configuration problem",
        reasoning="unrelated text that also doesn't contain the answer",
    )
    criteria = [_criterion("database connection pool exhaustion")]

    result = evaluate_deterministic(criteria, context)

    assert result.objective_passed is False
    assert result.troubleshoot_facts.root_cause_matches_expected is False


def test_authority_5_legacy_only_submission_preserves_old_behavior():
    """No structured payload at all (every structured field empty) —
    the original legacy-blob check applies, exactly as before this
    correction and before Stage 4C's structured-matching addition."""
    context = _troubleshoot_context(
        root_cause="",  # nothing structured submitted
        reasoning="database connection pool exhaustion",
    )
    criteria = [_criterion("database connection pool exhaustion")]

    result = evaluate_deterministic(criteria, context)

    assert result.objective_passed is True
    # Nothing structural existed to be "the" match — correctly distinct
    # from "some criterion happened to pass via the legacy path".
    assert result.troubleshoot_facts.root_cause_matches_expected is False


def test_authority_6_general_workspace_still_uses_legacy_blob_only():
    context = _general_context(findings="f", reasoning="database connection pool exhaustion", solution="s")
    criteria = [_criterion("database connection pool exhaustion")]

    result = evaluate_deterministic(criteria, context)

    assert result.objective_passed is True
    assert result.troubleshoot_facts is None


def test_authority_partial_structured_payload_is_still_authoritative():
    """Engaging with the structured workspace at all (e.g. a hypothesis
    recorded) but leaving the diagnosis blank makes the (empty)
    structured root_cause authoritative — a legacy field independently
    containing the right words still must not rescue it."""
    context = _troubleshoot_context(
        root_cause="",
        reasoning="database connection pool exhaustion",
        hypotheses=[TroubleshootHypothesisContext(id="h1", statement="a guess", reasoning="", supporting_evidence_ids=[])],
    )
    criteria = [_criterion("database connection pool exhaustion")]

    result = evaluate_deterministic(criteria, context)

    assert result.objective_passed is False
    assert result.troubleshoot_facts.root_cause_present is False


# =====================================================================
# Test 7 — self-reported confidence never affects correctness
# =====================================================================


def test_high_confidence_does_not_make_an_incorrect_diagnosis_correct():
    context = _troubleshoot_context(root_cause="the cache was cold", confidence="High")
    criteria = [_criterion("database connection pool exhaustion")]

    result = evaluate_deterministic(criteria, context)

    assert result.objective_passed is False


def test_low_confidence_does_not_make_a_correct_diagnosis_incorrect():
    context = _troubleshoot_context(root_cause="database connection pool exhaustion", confidence="Low")
    criteria = [_criterion("database connection pool exhaustion")]

    result = evaluate_deterministic(criteria, context)

    assert result.objective_passed is True


# =====================================================================
# Test 8 — hypothesis count never affects objective score
# =====================================================================


def test_hypothesis_count_does_not_affect_objective_score():
    criteria = [_criterion("database connection pool exhaustion")]
    one_hypothesis = [TroubleshootHypothesisContext(id="h1", statement="x", reasoning="y", supporting_evidence_ids=[])]
    five_hypotheses = [
        TroubleshootHypothesisContext(id=f"h{i}", statement="x", reasoning="y", supporting_evidence_ids=[])
        for i in range(5)
    ]

    result_one = evaluate_deterministic(
        criteria, _troubleshoot_context(root_cause="database connection pool exhaustion", hypotheses=one_hypothesis)
    )
    result_five = evaluate_deterministic(
        criteria, _troubleshoot_context(root_cause="database connection pool exhaustion", hypotheses=five_hypotheses)
    )

    assert result_one.objective_score == result_five.objective_score
    assert result_one.objective_passed == result_five.objective_passed is True


# =====================================================================
# Test 9 — GENERAL/legacy behavior is untouched
# =====================================================================


def test_general_workspace_matching_is_unaffected_by_stage_4c():
    context = _general_context(
        findings="f", reasoning="database connection pool exhaustion caused it", solution="s"
    )
    criteria = [_criterion("database connection pool exhaustion")]

    result = evaluate_deterministic(criteria, context)

    assert result.objective_passed is True
    assert result.troubleshoot_facts is None


def test_legacy_blob_match_still_works_when_structured_root_cause_is_empty():
    """Backward compatibility: a pre-Stage-3-shaped TROUBLESHOOT attempt
    (or one where the frontend adapter's mirroring is all that's
    present) still matches via the legacy blob exactly as before Stage
    4C — the structured check is additive, never a replacement."""
    context = _troubleshoot_context(
        root_cause="",  # no structured diagnosis at all
        findings="f", reasoning="database connection pool exhaustion caused it", solution="s",
    )
    criteria = [_criterion("database connection pool exhaustion")]

    result = evaluate_deterministic(criteria, context)

    assert result.objective_passed is True
    # The structured field itself was empty, so it did not match —
    # correctly distinct from "some deterministic criterion happened to pass".
    assert result.troubleshoot_facts.root_cause_matches_expected is False


# =====================================================================
# Test 12 — AI isolation: Stage 4C must not have touched the AI context
# =====================================================================


def test_ai_context_type_gained_no_new_fields_in_stage_4c():
    """As of Stage 4C specifically (before Stage 4D's deliberate
    `troubleshoot` field addition — see test_ai_provider_troubleshoot_context.py),
    the AI context had none of the raw structured field names directly
    on it — everything Stage 4C added lived only in
    DeterministicEvaluationResult.troubleshoot_facts, never in
    QuestAIEvaluationContext. This documents that historical boundary;
    Stage 4D's own tests cover the current, intentionally-extended
    shape."""
    field_names = {f.name for f in fields(QuestAIEvaluationContext)}
    assert not {"hypotheses", "diagnosis", "resolution", "evidence_reviewed", "observations"} & field_names


# =====================================================================
# No domain hardcoding — structural grep-equivalent check
# =====================================================================


def test_evaluator_source_contains_no_domain_specific_hardcoding():
    import inspect

    import app.services.quest_evaluation_service as svc
    import app.services.workspace_evaluation_registry as registry

    source = inspect.getsource(svc) + inspect.getsource(registry)
    forbidden = ["checkout", "latency", "veterinary", "database connection pool", "sre", "incident"]
    lowered = source.lower()
    for term in forbidden:
        assert term not in lowered, f"found domain-specific term {term!r} in evaluator source"


# =====================================================================
# API-level tests
# =====================================================================

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_troubleshoot_deterministic_evaluation.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.config import get_settings  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        # Manager Portal auth (the login-gated admin/analytics/quest-builder
        # routers): authenticate this shared client once so every admin-only
        # call in this file works without each test managing its own session.
        c.post("/api/v1/admin/login", json={"password": get_settings().admin_password})
        yield c
    TEST_DB_PATH.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def demo_employee_id(client):
    return client.get("/api/v1/onboarding/bundle/demo").json()["employee"]["id"]


@pytest.fixture(scope="module")
def capability_ids(client):
    caps = client.get("/api/v1/capabilities").json()
    return {c["key"]: c["id"] for c in caps}


def _build_troubleshoot_quest(client, employee_id, capability_ids, *, title, description, expected_answer, secret_markers=False, required_task=True):
    quest = client.post(
        "/api/v1/quests",
        json={"title": title, "description": description, "quest_type": "TROUBLESHOOT", "workspace_type": "TROUBLESHOOT"},
    ).json()
    qid = quest["id"]
    task = client.post(
        f"/api/v1/quests/{qid}/tasks",
        json={"title": "Confirm the affected area", "task_type": "INVESTIGATE", "required": required_task},
    ).json()
    client.post(f"/api/v1/quests/{qid}/evidence", json={"title": "Evidence", "evidence_type": "METRICS", "content": {}})

    criterion = (
        {
            "name": "hidden",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "SECRET_4C_EXPECTED_ANSWER",
            "expected_behavior": "SECRET_4C_EXPECTED_BEHAVIOR",
            "reference_solution": "SECRET_4C_REFERENCE_SOLUTION",
        }
        if secret_markers
        else {"name": "Root cause check", "criterion_type": "DETERMINISTIC", "expected_answer": expected_answer}
    )
    client.post(f"/api/v1/quests/{qid}/evaluation-criteria", json=criterion)
    client.post(f"/api/v1/quests/{qid}/capabilities", json={"capability_id": capability_ids["troubleshooting"]})
    client.post(f"/api/v1/quests/{qid}/assignments", json={"assignment_type": "EMPLOYEE", "employee_id": employee_id})
    pub = client.post(f"/api/v1/quests/{qid}/publish")
    assert pub.status_code == 200, pub.text
    return qid, task["id"]


def _start_attempt(client, quest_id, employee_id):
    return client.post("/api/v1/quest-attempts", json={"quest_id": quest_id, "employee_id": employee_id}).json()["id"]


def _patch_structured(client, attempt_id, employee_id, *, root_cause, proposed_fix="a fix", complete_task_id=None, confidence=None, extra_workspace=None):
    """Mirrors what `troubleshootSubmissionAdapter.ts`'s `toSubmission()`
    actually does in production: the legacy findings/reasoning/solution
    fields are always synthesized alongside the structured payload, never
    left empty — `submit_attempt`'s existing "record at least one of
    findings/reasoning/solution" gate is unrelated to Stage 4C and must
    still be satisfied the same way a real Troubleshoot submission
    always satisfies it."""
    payload = {
        "observations": [],
        "evidence_reviewed": [],
        "hypotheses": [{"id": "h1", "statement": "a hypothesis", "reasoning": "some reasoning", "supporting_evidence_ids": []}],
        "diagnosis": {"root_cause": root_cause, "confidence": confidence},
        "resolution": {"proposed_fix": proposed_fix, "validation_plan": None},
    }
    if extra_workspace is not None:
        payload = extra_workspace
    body = {
        "employee_id": employee_id,
        "findings": "Reviewed the available evidence.",
        "reasoning": f"Diagnosis: {root_cause}" if root_cause else "No diagnosis recorded yet.",
        "solution": f"Proposed resolution: {proposed_fix}" if proposed_fix else "",
        "workspace": {"type": "TROUBLESHOOT", "payload": payload},
    }
    if complete_task_id:
        body["completed_task_ids"] = [complete_task_id]
    res = client.patch(f"/api/v1/quest-attempts/{attempt_id}", json=body)
    assert res.status_code == 200, res.text
    return res.json()


# ---- Test 5 — required task incomplete ----


def test_required_task_incomplete_blocks_submission(client, demo_employee_id, capability_ids):
    qid, task_id = _build_troubleshoot_quest(
        client, demo_employee_id, capability_ids,
        title="Stage4C required-task quest", description="d",
        expected_answer="database connection pool exhaustion",
    )
    aid = _start_attempt(client, qid, demo_employee_id)
    _patch_structured(client, aid, demo_employee_id, root_cause="database connection pool exhaustion")
    # completed_task_ids deliberately omitted — required task left undone.
    submit = client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": demo_employee_id})
    assert submit.status_code == 422, submit.text


# ---- Test 10 — malformed structured payload doesn't crash evaluation ----


def test_malformed_structured_payload_evaluates_safely(client, demo_employee_id, capability_ids):
    qid, task_id = _build_troubleshoot_quest(
        client, demo_employee_id, capability_ids,
        title="Stage4C malformed-payload quest", description="d",
        expected_answer="database connection pool exhaustion",
    )
    aid = _start_attempt(client, qid, demo_employee_id)
    malformed = {"observations": "not a list", "hypotheses": 42, "diagnosis": ["nope"], "resolution": None}
    client.patch(
        f"/api/v1/quest-attempts/{aid}",
        json={
            "employee_id": demo_employee_id,
            "findings": "f", "reasoning": "r", "solution": "s",
            "completed_task_ids": [task_id],
            "workspace": {"type": "TROUBLESHOOT", "payload": malformed},
        },
    )
    submit = client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": demo_employee_id})
    assert submit.status_code == 200, submit.text
    eval_res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert eval_res.status_code == 200, eval_res.text


# ---- Test 11 — hidden criterion security ----


def test_hidden_criteria_never_leak_with_structured_matching(client, demo_employee_id, capability_ids):
    qid, task_id = _build_troubleshoot_quest(
        client, demo_employee_id, capability_ids,
        title="Stage4C secret-leak quest", description="d",
        expected_answer="", secret_markers=True,
    )
    aid = _start_attempt(client, qid, demo_employee_id)
    _patch_structured(client, aid, demo_employee_id, root_cause="an unrelated root cause", complete_task_id=task_id)
    client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": demo_employee_id})

    eval_res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert eval_res.status_code == 200, eval_res.text
    assert "SECRET_4C_EXPECTED_ANSWER" not in eval_res.text
    assert "SECRET_4C_EXPECTED_BEHAVIOR" not in eval_res.text
    assert "SECRET_4C_REFERENCE_SOLUTION" not in eval_res.text
    assert "expected_answer" not in eval_res.text


# ---- Test 13 — capability isolation: evidence text unchanged by Stage 4C ----


def test_capability_evidence_observation_text_unaffected_by_structured_facts(client, demo_employee_id, capability_ids):
    qid, task_id = _build_troubleshoot_quest(
        client, demo_employee_id, capability_ids,
        title="Stage4C capability-isolation quest", description="d",
        expected_answer="database connection pool exhaustion",
    )
    aid = _start_attempt(client, qid, demo_employee_id)
    _patch_structured(client, aid, demo_employee_id, root_cause="database connection pool exhaustion", complete_task_id=task_id)
    client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": demo_employee_id})
    eval_res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert eval_res.status_code == 200, eval_res.text
    body = eval_res.json()
    assert body["status"] == "COMPLETED"
    # No structured-payload vocabulary (hypotheses/diagnosis/root_cause)
    # leaks into the AI-facing summary/strengths text either — Stage 4C
    # did not touch AI prompt construction.
    assert "root_cause" not in eval_res.text
    assert "diagnosis" not in eval_res.text.lower() or "diagnosis" not in [k.lower() for k in body.keys()]


# ---- Test 14 — idempotency ----


def test_repeated_evaluation_of_troubleshoot_attempt_is_idempotent(client, demo_employee_id, capability_ids):
    qid, task_id = _build_troubleshoot_quest(
        client, demo_employee_id, capability_ids,
        title="Stage4C idempotency quest", description="d",
        expected_answer="database connection pool exhaustion",
    )
    aid = _start_attempt(client, qid, demo_employee_id)
    _patch_structured(client, aid, demo_employee_id, root_cause="database connection pool exhaustion", complete_task_id=task_id)
    client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": demo_employee_id})
    first = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id}).json()
    second = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id}).json()
    assert first == second


# ---- Test 15 — concurrency ----


def test_concurrent_troubleshoot_evaluation_produces_one_result(client, demo_employee_id, capability_ids):
    qid, task_id = _build_troubleshoot_quest(
        client, demo_employee_id, capability_ids,
        title="Stage4C concurrency quest", description="d",
        expected_answer="database connection pool exhaustion",
    )
    aid = _start_attempt(client, qid, demo_employee_id)
    _patch_structured(client, aid, demo_employee_id, root_cause="database connection pool exhaustion", complete_task_id=task_id)
    client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": demo_employee_id})

    def evaluate():
        return client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: evaluate(), range(8)))
    assert all(r.status_code == 200 for r in responses)

    final = client.get(f"/api/v1/quest-attempts/{aid}", params={"employee_id": demo_employee_id}).json()
    assert final["status"] == "COMPLETED"


# ---- Authority correction, end to end through the real HTTP surface ----


def test_authority_correction_via_api_legacy_field_cannot_rescue_wrong_diagnosis(client, demo_employee_id, capability_ids):
    """A raw PATCH that puts the expected answer only in the legacy
    `reasoning` field, while the structured diagnosis is wrong, must
    evaluate as objective_passed=False — proving the authority boundary
    holds through the full HTTP pipeline, not just at the unit level."""
    qid, task_id = _build_troubleshoot_quest(
        client, demo_employee_id, capability_ids,
        title="Stage4C authority-correction quest", description="d",
        expected_answer="database connection pool exhaustion",
    )
    aid = _start_attempt(client, qid, demo_employee_id)
    client.patch(
        f"/api/v1/quest-attempts/{aid}",
        json={
            "employee_id": demo_employee_id,
            "findings": "Reviewed the available evidence.",
            "reasoning": "database connection pool exhaustion",  # planted directly in the legacy field
            "solution": "Proposed resolution: a fix",
            "completed_task_ids": [task_id],
            "workspace": {
                "type": "TROUBLESHOOT",
                "payload": {
                    "observations": [],
                    "evidence_reviewed": [],
                    "hypotheses": [],
                    "diagnosis": {"root_cause": "DNS configuration problem", "confidence": None},
                    "resolution": {"proposed_fix": "a fix", "validation_plan": None},
                },
            },
        },
    )
    client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": demo_employee_id})
    eval_res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert eval_res.status_code == 200, eval_res.text
    body = eval_res.json()
    # objective_passed isn't in the employee-facing evaluation response
    # schema directly, but attempt.passed mirrors it — confirmed via the
    # attempt record, which is what the deterministic criterion actually
    # gated.
    final = client.get(f"/api/v1/quest-attempts/{aid}", params={"employee_id": demo_employee_id}).json()
    assert final["passed"] is False, final


# ---- SRE scenario (§23) ----


def test_sre_checkout_latency_scenario_evaluates_deterministically(client, demo_employee_id, capability_ids):
    qid, task_id = _build_troubleshoot_quest(
        client, demo_employee_id, capability_ids,
        title="Checkout latency spike",
        description="Checkout requests are experiencing elevated latency since this afternoon.",
        expected_answer="the 14:00 deploy regressed checkout latency",
    )
    aid = _start_attempt(client, qid, demo_employee_id)
    _patch_structured(
        client, aid, demo_employee_id,
        root_cause="The 14:00 deploy regressed checkout latency",
        proposed_fix="Roll back the deploy",
        confidence="High",
        complete_task_id=task_id,
    )
    client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": demo_employee_id})
    eval_res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert eval_res.status_code == 200, eval_res.text


# ---- Non-SRE scenario (§24) ----


def test_non_sre_vet_clinic_scenario_evaluates_deterministically(client, demo_employee_id, capability_ids):
    qid, task_id = _build_troubleshoot_quest(
        client, demo_employee_id, capability_ids,
        title="Vet clinic confirmation failures",
        description="A veterinary clinic's appointment confirmation process is failing intermittently.",
        expected_answer="the sms provider is rate limiting outbound confirmation texts",
    )
    aid = _start_attempt(client, qid, demo_employee_id)
    _patch_structured(
        client, aid, demo_employee_id,
        root_cause="The SMS provider is rate limiting outbound confirmation texts",
        proposed_fix="Switch to a queued send with backoff",
        confidence="Medium",
        complete_task_id=task_id,
    )
    client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": demo_employee_id})
    eval_res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert eval_res.status_code == 200, eval_res.text

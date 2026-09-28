"""Phase 7 Stage 4B backend tests: the EvaluationContext contract and the
workspace evaluation context registry — plumbing only, no scoring
changes.

Two groups of tests:

1. Pure unit tests against `evaluation_context.py` / `workspace_evaluation_registry.py`
   directly — no DB, no HTTP, no server. These cover the registry
   mapping and every defensive-parsing case (partial/malformed/legacy/
   unknown-workspace_type payloads) in isolation, fast and exhaustive.
2. API-level tests (isolated SQLite file, same convention as every other
   test_quest_*.py module) proving the refactored `evaluate_attempt`
   still produces the same outcomes end to end for GENERAL, correctly
   reconstructs TROUBLESHOOT's structured payload, and never leaks
   hidden evaluation data through the new context.
"""

from app.services.evaluation_context import (
    EvaluationAIContext,
    EvaluationCommonContext,
    EvaluationDeterministicContext,
    GeneralWorkspaceContext,
    TroubleshootDiagnosisContext,
    TroubleshootHypothesisContext,
    TroubleshootResolutionContext,
    TroubleshootWorkspaceContext,
    build_evaluation_context,
)
from app.services.workspace_evaluation_registry import (
    _build_general_context,
    _build_troubleshoot_context,
    resolve_workspace_context_builder,
)


class _FakeTask:
    """A bare stand-in for QuestTask — build_evaluation_context only
    reads `.id`/`.title`/`.required`, so a real ORM instance isn't
    needed for these pure unit tests."""

    def __init__(self, id, title, required):
        self.id = id
        self.title = title
        self.required = required


# =====================================================================
# Workspace resolver — Test 8 (registry mapping) / Test 9 (unknown type)
# =====================================================================


def test_resolver_maps_troubleshoot_to_its_builder():
    assert resolve_workspace_context_builder("TROUBLESHOOT") is _build_troubleshoot_context


def test_resolver_maps_general_to_the_general_builder():
    assert resolve_workspace_context_builder("GENERAL") is _build_general_context


def test_resolver_falls_back_to_general_for_unknown_workspace_type():
    """A workspace_type this build has never heard of (a future
    INVESTIGATION/DESIGN/BUILD/etc. not yet registered, or garbage data)
    must resolve to the safe empty fallback, never raise."""
    builder = resolve_workspace_context_builder("NOT_A_REAL_WORKSPACE_TYPE")
    assert builder is _build_general_context
    result = builder({"findings": "x"})
    assert result == GeneralWorkspaceContext()


# =====================================================================
# TROUBLESHOOT context builder — Test 3 (full), 4 (partial), 5 (malformed)
# =====================================================================


def test_troubleshoot_builder_reconstructs_a_complete_payload():
    submission = {
        "workspace": {
            "type": "TROUBLESHOOT",
            "payload": {
                "observations": ["latency climbing since 14:00"],
                "evidence_reviewed": ["ev-1", "ev-2"],
                "hypotheses": [
                    {
                        "id": "h1",
                        "statement": "The 14:00 deploy introduced a regression",
                        "reasoning": "Timing matches exactly",
                        "supporting_evidence_ids": ["ev-2"],
                    }
                ],
                "diagnosis": {"root_cause": "Deploy regressed checkout latency", "confidence": "High"},
                "resolution": {"proposed_fix": "Roll back the deploy", "validation_plan": "Watch p99 for 10 minutes"},
            },
        }
    }

    context = _build_troubleshoot_context(submission)

    assert isinstance(context, TroubleshootWorkspaceContext)
    assert context.observations == ["latency climbing since 14:00"]
    assert context.evidence_reviewed == ["ev-1", "ev-2"]
    assert context.hypotheses == [
        TroubleshootHypothesisContext(
            id="h1",
            statement="The 14:00 deploy introduced a regression",
            reasoning="Timing matches exactly",
            supporting_evidence_ids=["ev-2"],
        )
    ]
    assert context.diagnosis == TroubleshootDiagnosisContext(
        root_cause="Deploy regressed checkout latency", confidence="High"
    )
    assert context.resolution == TroubleshootResolutionContext(
        proposed_fix="Roll back the deploy", validation_plan="Watch p99 for 10 minutes"
    )


def test_troubleshoot_builder_handles_partial_payload():
    submission = {"workspace": {"type": "TROUBLESHOOT", "payload": {"observations": ["saw a spike"]}}}
    context = _build_troubleshoot_context(submission)

    assert context.observations == ["saw a spike"]
    assert context.evidence_reviewed == []
    assert context.hypotheses == []
    assert context.diagnosis == TroubleshootDiagnosisContext(root_cause="", confidence=None)
    assert context.resolution == TroubleshootResolutionContext(proposed_fix="", validation_plan=None)


def test_troubleshoot_builder_handles_missing_workspace_key():
    """Legacy attempt: no `workspace` key on the submission at all."""
    context = _build_troubleshoot_context({"findings": "x", "reasoning": "y", "solution": "z"})
    assert context == TroubleshootWorkspaceContext(
        observations=[],
        evidence_reviewed=[],
        hypotheses=[],
        diagnosis=TroubleshootDiagnosisContext(root_cause="", confidence=None),
        resolution=TroubleshootResolutionContext(proposed_fix="", validation_plan=None),
    )


def test_troubleshoot_builder_handles_null_workspace():
    context = _build_troubleshoot_context({"workspace": None})
    assert context.observations == []
    assert context.hypotheses == []


def test_troubleshoot_builder_handles_null_payload():
    context = _build_troubleshoot_context({"workspace": {"type": "TROUBLESHOOT", "payload": None}})
    assert context.observations == []
    assert context.diagnosis.root_cause == ""


def test_troubleshoot_builder_handles_malformed_field_types_without_crashing():
    """Every field holds the wrong type entirely — none of this may
    raise, and every field must default independently rather than the
    whole builder bailing out on the first surprise."""
    submission = {
        "workspace": {
            "type": "TROUBLESHOOT",
            "payload": {
                "observations": "not a list",
                "evidence_reviewed": 42,
                "hypotheses": "also not a list",
                "diagnosis": ["not", "a", "dict"],
                "resolution": 12345,
            },
        }
    }
    context = _build_troubleshoot_context(submission)

    assert context.observations == []
    assert context.evidence_reviewed == []
    assert context.hypotheses == []
    assert context.diagnosis == TroubleshootDiagnosisContext(root_cause="", confidence=None)
    assert context.resolution == TroubleshootResolutionContext(proposed_fix="", validation_plan=None)


def test_troubleshoot_builder_drops_malformed_individual_hypotheses():
    submission = {
        "workspace": {
            "type": "TROUBLESHOOT",
            "payload": {"hypotheses": [None, "garbage", 42, {"statement": "real one", "reasoning": "", "supporting_evidence_ids": []}]},
        }
    }
    context = _build_troubleshoot_context(submission)
    assert len(context.hypotheses) == 1
    assert context.hypotheses[0].statement == "real one"


def test_troubleshoot_builder_assigns_fallback_id_when_missing():
    submission = {
        "workspace": {
            "type": "TROUBLESHOOT",
            "payload": {"hypotheses": [{"statement": "no id given", "reasoning": "", "supporting_evidence_ids": []}]},
        }
    }
    context = _build_troubleshoot_context(submission)
    assert len(context.hypotheses) == 1
    assert isinstance(context.hypotheses[0].id, str) and context.hypotheses[0].id


def test_malformed_top_level_submission_types_do_not_crash_any_builder():
    for bad_submission in [{}, {"workspace": "not a dict"}, {"workspace": {"payload": "not a dict"}}]:
        general_result = _build_general_context(bad_submission)
        troubleshoot_result = _build_troubleshoot_context(bad_submission)
        assert general_result == GeneralWorkspaceContext()
        assert isinstance(troubleshoot_result, TroubleshootWorkspaceContext)


# =====================================================================
# build_evaluation_context — Test 1 (GENERAL legacy), 6 (legacy-only)
# =====================================================================


def test_build_evaluation_context_for_general_legacy_submission():
    """A GENERAL-workspace attempt with only the legacy fields (exactly
    what every quest looked like before Stage 3) must produce identical
    deterministic/ai inputs to what `_build_quest_context` always read
    directly off `attempt.submission` — same values, now typed."""
    submission = {
        "findings": "Error rate spiked at 14:02",
        "reasoning": "Correlated with the 14:00 deploy",
        "solution": "Rolled back and confirmed recovery",
        "completed_task_ids": ["task-1"],
    }
    tasks = [_FakeTask("task-1", "Confirm the root cause", True), _FakeTask("task-2", "Optional cleanup", False)]

    context = build_evaluation_context(
        employee_id="emp-1",
        quest_id="quest-1",
        quest_type="OTHER",
        workspace_type="GENERAL",
        attempt_id="attempt-1",
        submission=submission,
        quest_tasks=tasks,
    )

    assert context.common == EvaluationCommonContext(
        quest_id="quest-1", attempt_id="attempt-1", employee_id="emp-1", quest_type="OTHER", workspace_type="GENERAL"
    )
    assert context.deterministic == EvaluationDeterministicContext(
        findings="Error rate spiked at 14:02",
        reasoning="Correlated with the 14:00 deploy",
        solution="Rolled back and confirmed recovery",
        completed_task_ids={"task-1"},
        task_titles_completed=["Confirm the root cause"],
        task_titles_skipped=["Optional cleanup"],
    )
    assert context.ai == EvaluationAIContext(
        findings="Error rate spiked at 14:02",
        reasoning="Correlated with the 14:00 deploy",
        solution="Rolled back and confirmed recovery",
    )
    assert context.workspace == GeneralWorkspaceContext()


def test_build_evaluation_context_for_troubleshoot_legacy_only_submission():
    """A TROUBLESHOOT-workspace attempt with no `workspace` envelope at
    all (e.g. predates Stage 3, or the frontend never sent one) must
    still evaluate using the legacy fields — `workspace` degrades to an
    empty TroubleshootWorkspaceContext rather than crashing context
    construction."""
    submission = {"findings": "f", "reasoning": "r", "solution": "s", "completed_task_ids": []}
    context = build_evaluation_context(
        employee_id="emp-1",
        quest_id="quest-1",
        quest_type="TROUBLESHOOT",
        workspace_type="TROUBLESHOOT",
        attempt_id="attempt-1",
        submission=submission,
        quest_tasks=[],
    )
    assert context.deterministic.findings == "f"
    assert context.ai.findings == "f"
    assert isinstance(context.workspace, TroubleshootWorkspaceContext)
    assert context.workspace.hypotheses == []


def test_build_evaluation_context_missing_completed_task_ids_defaults_to_empty():
    context = build_evaluation_context(
        employee_id="e", quest_id="q", quest_type="OTHER", workspace_type="GENERAL",
        attempt_id="a", submission={}, quest_tasks=[_FakeTask("t1", "Task 1", True)],
    )
    assert context.deterministic.completed_task_ids == set()
    assert context.deterministic.task_titles_completed == []
    assert context.deterministic.task_titles_skipped == []  # required task, not "skipped" (skipped = optional+incomplete)


# =====================================================================
# API-level: GENERAL unchanged, TROUBLESHOOT structured evaluation,
# hidden-data non-leakage — Test 2, 3 (end-to-end), 7
# =====================================================================

import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_evaluation_context.db"
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


def _build_quest(client, employee_id, capability_ids, *, workspace_type, quest_type, secret_markers=False):
    quest = client.post(
        "/api/v1/quests",
        json={
            "title": f"Stage4B {workspace_type} quest",
            "description": "A quest used only to exercise the evaluation context refactor.",
            "quest_type": quest_type,
            "workspace_type": workspace_type,
        },
    ).json()
    qid = quest["id"]
    client.post(f"/api/v1/quests/{qid}/tasks", json={"title": "Confirm the root cause", "task_type": "INVESTIGATE", "required": True})
    client.post(f"/api/v1/quests/{qid}/evidence", json={"title": "Evidence", "evidence_type": "METRICS", "content": {}})

    criterion = (
        {
            "name": "hidden",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "SECRET_4B_EXPECTED_ANSWER",
            "expected_behavior": "SECRET_4B_EXPECTED_BEHAVIOR",
            "reference_solution": "SECRET_4B_REFERENCE_SOLUTION",
        }
        if secret_markers
        else {"name": "quality", "criterion_type": "QUALITATIVE", "description": "reasoning quality"}
    )
    client.post(f"/api/v1/quests/{qid}/evaluation-criteria", json=criterion)
    client.post(f"/api/v1/quests/{qid}/capabilities", json={"capability_id": capability_ids["troubleshooting"]})
    client.post(f"/api/v1/quests/{qid}/assignments", json={"assignment_type": "EMPLOYEE", "employee_id": employee_id})
    pub = client.post(f"/api/v1/quests/{qid}/publish")
    assert pub.status_code == 200, pub.text
    return qid


def test_general_quest_evaluation_unchanged_after_refactor(client, demo_employee_id, capability_ids):
    """Test 2 — GENERAL structured/normal submission: existing behavior
    remains intact after the EvaluationContext refactor."""
    qid = _build_quest(client, demo_employee_id, capability_ids, workspace_type="GENERAL", quest_type="OTHER")
    attempt = client.post("/api/v1/quest-attempts", json={"quest_id": qid, "employee_id": demo_employee_id}).json()
    aid = attempt["id"]
    task_id = client.get(f"/api/v1/quests/{qid}/employee", params={"employee_id": demo_employee_id}).json()["tasks"][0]["id"]
    client.patch(
        f"/api/v1/quest-attempts/{aid}",
        json={
            "employee_id": demo_employee_id,
            "findings": "Clear signal in the metrics",
            "reasoning": "Correlated with a recent change",
            "solution": "Reverted the change",
            "completed_task_ids": [task_id],
        },
    )
    client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": demo_employee_id})

    eval_res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert eval_res.status_code == 200, eval_res.text
    body = eval_res.json()
    assert body["status"] == "COMPLETED"
    assert len(body["capabilities"]) >= 1


def test_troubleshoot_structured_submission_evaluates_successfully(client, demo_employee_id, capability_ids):
    """Test 3 (end-to-end) — the refactored evaluator correctly
    processes a fully structured TROUBLESHOOT submission via the new
    TroubleshootWorkspaceContext builder, producing the same kind of
    outcome (COMPLETED, capability evidence) as before."""
    qid = _build_quest(client, demo_employee_id, capability_ids, workspace_type="TROUBLESHOOT", quest_type="TROUBLESHOOT")
    attempt = client.post("/api/v1/quest-attempts", json={"quest_id": qid, "employee_id": demo_employee_id}).json()
    aid = attempt["id"]
    task_id = client.get(f"/api/v1/quests/{qid}/employee", params={"employee_id": demo_employee_id}).json()["tasks"][0]["id"]
    client.patch(
        f"/api/v1/quest-attempts/{aid}",
        json={
            "employee_id": demo_employee_id,
            "findings": "Reviewed 1 evidence source: Evidence.",
            "reasoning": "Hypothesis: deploy caused it. Diagnosis: confirmed deploy regression.",
            "solution": "Proposed resolution: roll back.",
            "completed_task_ids": [task_id],
            "workspace": {
                "type": "TROUBLESHOOT",
                "payload": {
                    "observations": ["spike observed"],
                    "evidence_reviewed": ["ev-1"],
                    "hypotheses": [
                        {"id": "h1", "statement": "deploy caused it", "reasoning": "timing matches", "supporting_evidence_ids": ["ev-1"]}
                    ],
                    "diagnosis": {"root_cause": "deploy regression", "confidence": "High"},
                    "resolution": {"proposed_fix": "roll back", "validation_plan": "watch metrics"},
                },
            },
        },
    )
    client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": demo_employee_id})

    eval_res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert eval_res.status_code == 200, eval_res.text
    assert eval_res.json()["status"] == "COMPLETED"

    # The structured payload must still be exactly as submitted —
    # Stage 4B reads it, never mutates or strips it.
    final = client.get(f"/api/v1/quest-attempts/{aid}", params={"employee_id": demo_employee_id}).json()
    assert final["submission"]["workspace"]["payload"]["diagnosis"]["root_cause"] == "deploy regression"


def test_hidden_evaluation_data_never_leaks_through_the_new_context(client, demo_employee_id, capability_ids):
    """Test 7 — expected_answer/expected_behavior/reference_solution/
    max_score must not reach any employee-facing response, for either
    workspace type, after the EvaluationContext refactor."""
    for workspace_type, quest_type in [("GENERAL", "OTHER"), ("TROUBLESHOOT", "TROUBLESHOOT")]:
        qid = _build_quest(
            client, demo_employee_id, capability_ids, workspace_type=workspace_type, quest_type=quest_type, secret_markers=True
        )
        attempt = client.post("/api/v1/quest-attempts", json={"quest_id": qid, "employee_id": demo_employee_id}).json()
        aid = attempt["id"]
        task_id = client.get(f"/api/v1/quests/{qid}/employee", params={"employee_id": demo_employee_id}).json()["tasks"][0]["id"]
        client.patch(
            f"/api/v1/quest-attempts/{aid}",
            json={
                "employee_id": demo_employee_id,
                "findings": "unrelated finding",
                "reasoning": "unrelated reasoning",
                "solution": "unrelated solution",
                "completed_task_ids": [task_id],
            },
        )
        client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": demo_employee_id})

        eval_res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
        assert eval_res.status_code == 200, eval_res.text
        assert "SECRET_4B_EXPECTED_ANSWER" not in eval_res.text
        assert "SECRET_4B_EXPECTED_BEHAVIOR" not in eval_res.text
        assert "SECRET_4B_REFERENCE_SOLUTION" not in eval_res.text
        assert "expected_answer" not in eval_res.text
        assert "expected_behavior" not in eval_res.text
        assert "reference_solution" not in eval_res.text

        get_res = client.get(f"/api/v1/quest-attempts/{aid}/evaluation", params={"employee_id": demo_employee_id})
        assert "SECRET_4B_EXPECTED_ANSWER" not in get_res.text
        assert "SECRET_4B_REFERENCE_SOLUTION" not in get_res.text


def test_evaluation_context_dataclasses_have_no_field_capable_of_holding_hidden_data():
    """Structural guarantee, independent of any live server: none of the
    EvaluationContext dataclasses declare a field that could hold
    expected_answer/expected_behavior/reference_solution/max_score, so
    there is nothing for a future change to accidentally populate."""
    import dataclasses

    hidden_names = {"expected_answer", "expected_behavior", "reference_solution", "max_score"}
    for cls in [
        EvaluationCommonContext,
        EvaluationDeterministicContext,
        EvaluationAIContext,
        GeneralWorkspaceContext,
        TroubleshootWorkspaceContext,
        TroubleshootHypothesisContext,
        TroubleshootDiagnosisContext,
        TroubleshootResolutionContext,
    ]:
        field_names = {f.name for f in dataclasses.fields(cls)}
        assert not (field_names & hidden_names), f"{cls.__name__} unexpectedly has a hidden-data field"

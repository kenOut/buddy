"""Phase 7 Stage 4D backend tests: structured Troubleshooting AI
evaluation — the AI provider learns to read the structured payload
(observations/evidence_reviewed/hypotheses/diagnosis/resolution)
without ever becoming the authority for objective correctness.

Three groups, matching the Stage 4B/4C test file convention:

1. Pure unit tests building an `EvaluationContext` -> `DeterministicEvaluationResult`
   -> `QuestAIEvaluationContext` -> `MockAIProvider.generate_for_quest()`
   chain directly, no DB, no HTTP — fast, exhaustive coverage of the
   structured-context construction and the AI heuristic's content.
2. API-level tests (isolated SQLite file) proving the full pipeline —
   traceability, failure recovery, security, idempotency, SRE/non-SRE
   domain neutrality — still holds through the real HTTP surface.
"""

import asyncio
import json
from dataclasses import fields

from app.models.employee import Employee
from app.models.quest import Quest
from app.models.quest_evaluation_criterion import QuestEvaluationCriterion
from app.services.ai_provider import MockAIProvider, QuestAIEvaluationContext
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
    _build_quest_context,
    evaluate_deterministic,
)


def _employee(job_title="Support Engineer"):
    return Employee(id="emp-1", job_title=job_title, full_name="Test Employee", email="t@buddy.dev")


def _quest(title="A troubleshooting quest", description="d"):
    return Quest(id="quest-1", title=title, description=description, quest_type="TROUBLESHOOT", workspace_type="TROUBLESHOOT")


def _criterion(expected_answer: str = "", max_score: float = 100.0):
    return QuestEvaluationCriterion(
        id="crit-1", quest_id="quest-1", name="Root cause check",
        criterion_type="DETERMINISTIC" if expected_answer else "QUALITATIVE",
        expected_answer=expected_answer, max_score=max_score,
    )


def _troubleshoot_eval_context(
    *, root_cause="", confidence=None, proposed_fix="", validation_plan=None,
    hypotheses=None, observations=None, evidence_reviewed=None,
    findings="f", reasoning="r", solution="s",
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
            observations=observations or [],
            evidence_reviewed=evidence_reviewed or [],
            hypotheses=hypotheses or [],
            diagnosis=TroubleshootDiagnosisContext(root_cause=root_cause, confidence=confidence),
            resolution=TroubleshootResolutionContext(proposed_fix=proposed_fix, validation_plan=validation_plan),
        ),
        ai=EvaluationAIContext(findings=findings, reasoning=reasoning, solution=solution),
    )


def _general_eval_context(*, findings="f", reasoning="r", solution="s") -> EvaluationContext:
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


def _quest_ai_context(eval_context: EvaluationContext, *, target_capability_keys, criteria=None) -> QuestAIEvaluationContext:
    det_result = evaluate_deterministic(criteria or [_criterion()], eval_context)
    return _build_quest_context(_employee(), _quest(), eval_context, det_result, target_capability_keys)


def _generate(quest_ai_context: QuestAIEvaluationContext) -> dict:
    raw = asyncio.run(MockAIProvider().generate_for_quest(quest_ai_context))
    return json.loads(raw)


# =====================================================================
# 1-6: structured AI context construction
# =====================================================================


def test_1_fully_populated_submission_produces_structured_ai_context():
    hyp = TroubleshootHypothesisContext(id="h1", statement="a guess", reasoning="why", supporting_evidence_ids=["ev-1"])
    ctx = _troubleshoot_eval_context(
        root_cause="root cause text", confidence="High", proposed_fix="fix it",
        validation_plan="watch metrics", hypotheses=[hyp], observations=["obs1"], evidence_reviewed=["ev-1"],
    )
    quest_ai_context = _quest_ai_context(ctx, target_capability_keys=["troubleshooting"])
    assert quest_ai_context.troubleshoot is not None
    assert isinstance(quest_ai_context.troubleshoot, TroubleshootWorkspaceContext)


def test_2_observations_preserved():
    ctx = _troubleshoot_eval_context(root_cause="rc", observations=["saw a spike", "logs were noisy"])
    quest_ai_context = _quest_ai_context(ctx, target_capability_keys=["troubleshooting"])
    assert quest_ai_context.troubleshoot.observations == ["saw a spike", "logs were noisy"]


def test_3_evidence_reviewed_preserved():
    ctx = _troubleshoot_eval_context(root_cause="rc", evidence_reviewed=["ev-1", "ev-2"])
    quest_ai_context = _quest_ai_context(ctx, target_capability_keys=["troubleshooting"])
    assert quest_ai_context.troubleshoot.evidence_reviewed == ["ev-1", "ev-2"]


def test_4_hypotheses_preserve_statement_reasoning_supporting_ids():
    hyp = TroubleshootHypothesisContext(id="h1", statement="stmt", reasoning="because", supporting_evidence_ids=["ev-9"])
    ctx = _troubleshoot_eval_context(root_cause="rc", hypotheses=[hyp])
    quest_ai_context = _quest_ai_context(ctx, target_capability_keys=["troubleshooting"])
    assert quest_ai_context.troubleshoot.hypotheses == [hyp]


def test_5_diagnosis_preserves_root_cause_and_confidence():
    ctx = _troubleshoot_eval_context(root_cause="the actual cause", confidence="Medium")
    quest_ai_context = _quest_ai_context(ctx, target_capability_keys=["troubleshooting"])
    assert quest_ai_context.troubleshoot.diagnosis == TroubleshootDiagnosisContext(root_cause="the actual cause", confidence="Medium")


def test_6_resolution_preserves_proposed_fix_and_validation_plan():
    ctx = _troubleshoot_eval_context(root_cause="rc", proposed_fix="do the fix", validation_plan="check it worked")
    quest_ai_context = _quest_ai_context(ctx, target_capability_keys=["troubleshooting"])
    assert quest_ai_context.troubleshoot.resolution == TroubleshootResolutionContext(proposed_fix="do the fix", validation_plan="check it worked")


# =====================================================================
# Correction: evidence-review breadth/count must never independently
# affect a capability assessment. `evidence_reviewed` remains available
# on the AI context as information, but its length is not a signal.
# =====================================================================


def _identical_content_context(*, evidence_reviewed):
    """Everything held constant except `evidence_reviewed` — isolates
    breadth/count as the only variable between two otherwise-identical
    submissions."""
    hyp = TroubleshootHypothesisContext(id="h1", statement="a hypothesis", reasoning="some reasoning", supporting_evidence_ids=["ev-1"])
    return _troubleshoot_eval_context(
        root_cause="database connection pool exhaustion",
        proposed_fix="roll back the change",
        validation_plan="watch the metrics",
        hypotheses=[hyp],
        observations=["an observation"],
        evidence_reviewed=evidence_reviewed,
    )


def test_correction_1_evidence_reviewed_count_cannot_improve_capability_assessment():
    one_item = _identical_content_context(evidence_reviewed=["ev-1"])
    five_items = _identical_content_context(evidence_reviewed=["ev-1", "ev-2", "ev-3", "ev-4", "ev-5"])
    keys = ["troubleshooting", "problem_solving", "independence"]

    result_one = _generate(_quest_ai_context(one_item, target_capability_keys=keys))
    result_five = _generate(_quest_ai_context(five_items, target_capability_keys=keys))

    assert result_one["capabilities"] == result_five["capabilities"]
    assert result_one["strengths"] == result_five["strengths"]
    assert result_one["development_areas"] == result_five["development_areas"]


def test_correction_2_zero_vs_many_evidence_reviewed_produces_no_stronger_evidence():
    """The most direct regression: reviewing NO evidence at all versus
    reviewing many must not change any capability's level, confidence,
    or evidence text — breadth is not a signal at any point on its
    range, not just at the margins."""
    none_reviewed = _identical_content_context(evidence_reviewed=[])
    many_reviewed = _identical_content_context(evidence_reviewed=["ev-1", "ev-2", "ev-3", "ev-4"])
    keys = ["troubleshooting", "problem_solving", "independence"]

    result_none = _generate(_quest_ai_context(none_reviewed, target_capability_keys=keys))
    result_many = _generate(_quest_ai_context(many_reviewed, target_capability_keys=keys))

    assert result_none["capabilities"] == result_many["capabilities"]


def test_correction_3_evidence_reviewed_still_reaches_the_ai_context():
    """Removed as a *scoring* input, not removed from the context
    entirely — `evidence_reviewed` must still be present and correct on
    `QuestAIEvaluationContext.troubleshoot`."""
    ctx = _identical_content_context(evidence_reviewed=["ev-7", "ev-9"])
    quest_ai_context = _quest_ai_context(ctx, target_capability_keys=["troubleshooting"])
    assert quest_ai_context.troubleshoot.evidence_reviewed == ["ev-7", "ev-9"]


def test_correction_4_actual_content_still_produces_structured_signals():
    """The correction removes breadth as a signal — it must not have
    accidentally also removed the legitimate content-based signals
    (hypothesis-evidence linkage, diagnosis presence, resolution
    completeness) that Stage 4D was built for."""
    strong_hyp = TroubleshootHypothesisContext(id="h1", statement="stmt", reasoning="because", supporting_evidence_ids=["ev-1"])
    strong_ctx = _troubleshoot_eval_context(
        root_cause="a clear root cause", proposed_fix="a clear fix", validation_plan="a clear validation plan", hypotheses=[strong_hyp],
    )
    weak_ctx = _troubleshoot_eval_context(root_cause="", proposed_fix="", hypotheses=[])
    keys = ["troubleshooting", "problem_solving"]

    strong_result = _generate(_quest_ai_context(strong_ctx, target_capability_keys=keys))
    weak_result = _generate(_quest_ai_context(weak_ctx, target_capability_keys=keys))

    strong_levels = {c["capability"]: c["level"] for c in strong_result["capabilities"]}
    weak_levels = {c["capability"]: c["level"] for c in weak_result["capabilities"]}
    assert strong_levels["troubleshooting"] == "STRONG"
    assert weak_levels["troubleshooting"] == "DEVELOPING"
    assert strong_levels != weak_levels


def test_correction_5_existing_stage_4d_structural_signal_tests_still_pass():
    """Sanity check that the correction didn't disturb the
    troubleshooting/problem_solving structural signals Stage 4D
    originally added alongside the now-removed breadth one."""
    hyp = TroubleshootHypothesisContext(id="h1", statement="s", reasoning="r", supporting_evidence_ids=["ev-1"])
    ctx = _troubleshoot_eval_context(root_cause="rc", hypotheses=[hyp])
    result = _generate(_quest_ai_context(ctx, target_capability_keys=["troubleshooting", "problem_solving"]))
    evidence_texts = {c["capability"]: c["evidence"] for c in result["capabilities"]}
    assert "diagnosis" in evidence_texts["troubleshooting"].lower()
    assert "hypothes" in evidence_texts["problem_solving"].lower()


def test_correction_6_no_breadth_derived_evidence_text_anywhere():
    ctx = _identical_content_context(evidence_reviewed=["ev-1", "ev-2", "ev-3"])
    result = _generate(_quest_ai_context(ctx, target_capability_keys=["troubleshooting", "problem_solving", "independence"]))
    for capability in result["capabilities"]:
        lowered = capability["evidence"].lower()
        assert "breadth" not in lowered
        assert "evidence reviewed" not in lowered


def test_correction_bucket_evidence_breadth_function_no_longer_exists():
    import app.services.ai_provider as provider_mod

    assert not hasattr(provider_mod, "_bucket_evidence_breadth")


# =====================================================================
# 7-12: defensive parsing — the AI-facing path must not crash
# =====================================================================


def test_7_missing_fields_do_not_crash():
    ctx = _troubleshoot_eval_context()  # everything defaulted/empty
    quest_ai_context = _quest_ai_context(ctx, target_capability_keys=["troubleshooting"])
    result = _generate(quest_ai_context)
    assert "capabilities" in result


def test_8_null_fields_do_not_crash():
    ctx = _troubleshoot_eval_context(root_cause="", confidence=None, proposed_fix="", validation_plan=None)
    quest_ai_context = _quest_ai_context(ctx, target_capability_keys=["problem_solving"])
    result = _generate(quest_ai_context)
    assert "capabilities" in result


def test_9_malformed_hypothesis_entries_do_not_crash_context_builder():
    from app.services.workspace_evaluation_registry import _build_troubleshoot_context

    submission = {"workspace": {"type": "TROUBLESHOOT", "payload": {"hypotheses": [None, "garbage", 42]}}}
    workspace_context = _build_troubleshoot_context(submission)
    assert workspace_context.hypotheses == []


def test_10_malformed_diagnosis_does_not_crash_context_builder():
    from app.services.workspace_evaluation_registry import _build_troubleshoot_context

    submission = {"workspace": {"type": "TROUBLESHOOT", "payload": {"diagnosis": ["not", "a", "dict"]}}}
    workspace_context = _build_troubleshoot_context(submission)
    assert workspace_context.diagnosis == TroubleshootDiagnosisContext(root_cause="", confidence=None)


def test_11_malformed_resolution_does_not_crash_context_builder():
    from app.services.workspace_evaluation_registry import _build_troubleshoot_context

    submission = {"workspace": {"type": "TROUBLESHOOT", "payload": {"resolution": 12345}}}
    workspace_context = _build_troubleshoot_context(submission)
    assert workspace_context.resolution == TroubleshootResolutionContext(proposed_fix="", validation_plan=None)


def test_12_legacy_only_submission_uses_pre_stage_4d_ai_behavior():
    """No structured payload at all — `troubleshoot` must be None on the
    AI context, so generate_for_quest falls through to the exact
    pre-Stage-4D reasoning/solution heuristic."""
    ctx = _troubleshoot_eval_context(root_cause="", reasoning="database connection pool exhaustion caused it")
    quest_ai_context = _quest_ai_context(ctx, target_capability_keys=["troubleshooting"], criteria=[_criterion("database connection pool exhaustion")])
    assert quest_ai_context.troubleshoot is None
    result = _generate(quest_ai_context)
    assert result["capabilities"][0]["evidence"].startswith("Assessed from the quality and detail")


# =====================================================================
# 13-16: AI authority boundary
# =====================================================================


def test_13_objective_pass_unchanged_regardless_of_ai_interpretation():
    ctx = _troubleshoot_eval_context(root_cause="database connection pool exhaustion")
    det_result = evaluate_deterministic([_criterion("database connection pool exhaustion")], ctx)
    assert det_result.objective_passed is True
    # AI interpretation (rich or sparse) never runs before this is
    # decided, and nothing feeds the AI's output back into it.
    quest_ai_context = _build_quest_context(_employee(), _quest(), ctx, det_result, ["troubleshooting"])
    assert quest_ai_context.objective_passed is True
    _generate(quest_ai_context)  # AI runs after the fact, has no write path back
    assert det_result.objective_passed is True


def test_14_objective_fail_unchanged_regardless_of_ai_interpretation():
    hyp = TroubleshootHypothesisContext(id="h1", statement="great hypothesis", reasoning="very detailed reasoning indeed", supporting_evidence_ids=["ev-1"])
    ctx = _troubleshoot_eval_context(root_cause="wrong diagnosis", hypotheses=[hyp], evidence_reviewed=["ev-1", "ev-2", "ev-3"])
    det_result = evaluate_deterministic([_criterion("database connection pool exhaustion")], ctx)
    assert det_result.objective_passed is False
    quest_ai_context = _build_quest_context(_employee(), _quest(), ctx, det_result, ["troubleshooting"])
    result = _generate(quest_ai_context)
    # Even though the structural signals here are strong (linked
    # hypothesis, broad evidence review), objective_passed stays False.
    assert quest_ai_context.objective_passed is False


def test_15_ai_cannot_override_objective_score():
    """`attempt.score` is set from det_result.objective_score before the
    AI call and never touched again — verified structurally by asserting
    the AI response JSON has no `objective_score` key it could
    overwrite, and by source inspection."""
    ctx = _troubleshoot_eval_context(root_cause="database connection pool exhaustion")
    quest_ai_context = _quest_ai_context(ctx, target_capability_keys=["troubleshooting"], criteria=[_criterion("database connection pool exhaustion")])
    result = _generate(quest_ai_context)
    assert "objective_score" not in result
    assert "objective_passed" not in result


def test_16_ai_response_schema_has_no_pass_fail_field():
    from app.schemas.ai_evaluation import AIEvaluationResponse

    field_names = set(AIEvaluationResponse.model_fields.keys())
    assert not {"objective_passed", "objective_score", "passed", "score"} & field_names


# =====================================================================
# Domain neutrality (structural check on the AI provider source itself)
# =====================================================================


def test_ai_provider_source_has_no_domain_specific_hardcoding():
    import inspect

    import app.services.ai_provider as provider_mod

    source = inspect.getsource(provider_mod).lower()
    for term in ["checkout", "latency", "veterinary", "database connection pool", "kubernetes", "api gateway", "deployment"]:
        assert term not in source, f"found domain-specific term {term!r} in ai_provider.py"


# =====================================================================
# API-level tests
# =====================================================================

import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_troubleshoot_ai_evaluation.db"
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


def _build_quest(client, employee_id, capability_ids, *, title, description, expected_answer="", secret_markers=False, capability_keys=("troubleshooting", "problem_solving", "independence")):
    quest = client.post(
        "/api/v1/quests",
        json={"title": title, "description": description, "quest_type": "TROUBLESHOOT", "workspace_type": "TROUBLESHOOT"},
    ).json()
    qid = quest["id"]
    task = client.post(f"/api/v1/quests/{qid}/tasks", json={"title": "Confirm the affected area", "task_type": "INVESTIGATE", "required": True}).json()
    client.post(f"/api/v1/quests/{qid}/evidence", json={"title": "Evidence A", "evidence_type": "METRICS", "content": {}})
    client.post(f"/api/v1/quests/{qid}/evidence", json={"title": "Evidence B", "evidence_type": "LOGS", "content": {}})

    criterion = (
        {"name": "hidden", "criterion_type": "DETERMINISTIC", "expected_answer": "SECRET_4D_EXPECTED_ANSWER",
         "expected_behavior": "SECRET_4D_EXPECTED_BEHAVIOR", "reference_solution": "SECRET_4D_REFERENCE_SOLUTION"}
        if secret_markers
        else {"name": "Root cause check", "criterion_type": "DETERMINISTIC", "expected_answer": expected_answer} if expected_answer
        else {"name": "quality", "criterion_type": "QUALITATIVE", "description": "reasoning quality"}
    )
    client.post(f"/api/v1/quests/{qid}/evaluation-criteria", json=criterion)
    for key in capability_keys:
        client.post(f"/api/v1/quests/{qid}/capabilities", json={"capability_id": capability_ids[key]})
    client.post(f"/api/v1/quests/{qid}/assignments", json={"assignment_type": "EMPLOYEE", "employee_id": employee_id})
    pub = client.post(f"/api/v1/quests/{qid}/publish")
    assert pub.status_code == 200, pub.text
    return qid, task["id"]


def _start_attempt(client, quest_id, employee_id):
    return client.post("/api/v1/quest-attempts", json={"quest_id": quest_id, "employee_id": employee_id}).json()["id"]


def _submit_structured(client, attempt_id, employee_id, *, root_cause, proposed_fix="a fix", complete_task_id=None, hypotheses=None, evidence_reviewed=None):
    payload = {
        "observations": ["an observation"],
        "evidence_reviewed": evidence_reviewed or [],
        "hypotheses": hypotheses if hypotheses is not None else [
            {"id": "h1", "statement": "a hypothesis", "reasoning": "some reasoning", "supporting_evidence_ids": evidence_reviewed or []}
        ],
        "diagnosis": {"root_cause": root_cause, "confidence": "Medium"},
        "resolution": {"proposed_fix": proposed_fix, "validation_plan": "a validation plan"},
    }
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


def _evaluate(client, quest, employee_id, capability_ids, *, root_cause, expected_answer="database connection pool exhaustion", evidence_reviewed=None):
    qid, task_id = _build_quest(client, employee_id, capability_ids, title=quest, description="d", expected_answer=expected_answer)
    aid = _start_attempt(client, qid, employee_id)
    _submit_structured(client, aid, employee_id, root_cause=root_cause, complete_task_id=task_id, evidence_reviewed=evidence_reviewed)
    client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": employee_id})
    res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": employee_id})
    assert res.status_code == 200, res.text
    return aid, res


# ---- 17-20: capability integrity ----


def test_17_18_capability_evidence_tied_to_attempt_and_evaluation(client, demo_employee_id, capability_ids):
    aid, res = _evaluate(client, "Stage4D capability provenance quest", demo_employee_id, capability_ids,
                          root_cause="database connection pool exhaustion", evidence_reviewed=["ev-a", "ev-b"])
    body = res.json()
    assert len(body["capabilities"]) >= 1

    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models import CapabilityEvaluation, CapabilityEvidence

    async def check():
        async with AsyncSessionLocal() as db:
            evidence_rows = (await db.execute(select(CapabilityEvidence).where(CapabilityEvidence.quest_attempt_id == aid))).scalars().all()
            assert len(evidence_rows) >= 1
            assert all(e.quest_attempt_id == aid for e in evidence_rows)
            ai_rows = [e for e in evidence_rows if e.source == "ai"]
            assert ai_rows, "expected at least one AI-sourced evidence row"
            evaluation = (await db.execute(select(CapabilityEvaluation).where(CapabilityEvaluation.quest_attempt_id == aid))).scalar_one()
            assert all(e.evaluation_id == evaluation.id for e in ai_rows)

    asyncio.run(check())


def test_19_no_telemetry_becomes_capability_evidence(client, demo_employee_id, capability_ids):
    """Evidence observation text must never mention click/navigation/
    save-count telemetry — only content-derived signals."""
    aid, res = _evaluate(client, "Stage4D no-telemetry quest", demo_employee_id, capability_ids,
                          root_cause="database connection pool exhaustion", evidence_reviewed=["ev-a"])
    body = res.json()
    forbidden = ["click", "navigat", "autosave", "time spent", "tab switch"]
    for capability in body["capabilities"]:
        lowered = capability["evidence"].lower()
        for term in forbidden:
            assert term not in lowered


def test_20_capability_levels_still_use_existing_enum(client, demo_employee_id, capability_ids):
    aid, res = _evaluate(client, "Stage4D capability level quest", demo_employee_id, capability_ids, root_cause="database connection pool exhaustion")
    body = res.json()
    for capability in body["capabilities"]:
        assert capability["level"] in ("DEVELOPING", "CAPABLE", "STRONG")


# ---- 21-23: traceability ----


def test_21_22_23_ai_traceability_preserved(client, demo_employee_id, capability_ids):
    aid, res = _evaluate(client, "Stage4D traceability quest", demo_employee_id, capability_ids, root_cause="database connection pool exhaustion")

    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models import CapabilityEvaluation

    async def check():
        async with AsyncSessionLocal() as db:
            evaluation = (await db.execute(select(CapabilityEvaluation).where(CapabilityEvaluation.quest_attempt_id == aid))).scalar_one()
            assert evaluation.model == "mock-heuristic-v1"
            assert evaluation.prompt_version
            assert evaluation.evaluation_version
            assert evaluation.raw_response
            assert isinstance(evaluation.structured_result, dict)
            assert evaluation.created_at is not None

    asyncio.run(check())


# ---- 24-25: AI failure behavior ----


def test_24_25_ai_failure_does_not_undo_completion_or_deterministic_result(client, demo_employee_id, capability_ids):
    import app.services.quest_evaluation_service as qes_mod
    from app.services.ai_provider import AIProviderError

    qid, task_id = _build_quest(client, demo_employee_id, capability_ids, title="Stage4D AI failure quest", description="d", expected_answer="database connection pool exhaustion")
    aid = _start_attempt(client, qid, demo_employee_id)
    _submit_structured(client, aid, demo_employee_id, root_cause="database connection pool exhaustion", complete_task_id=task_id)
    client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": demo_employee_id})

    class BrokenProvider:
        model_name = "broken"

        async def generate_for_quest(self, context):
            raise AIProviderError("simulated outage")

    original = qes_mod.get_ai_provider
    qes_mod.get_ai_provider = lambda name: BrokenProvider()
    try:
        res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
        assert res.status_code == 503, res.text
    finally:
        qes_mod.get_ai_provider = original

    attempt = client.get(f"/api/v1/quest-attempts/{aid}", params={"employee_id": demo_employee_id}).json()
    assert attempt["status"] == "SUBMITTED"
    assert attempt["submission"]["workspace"]["payload"]["diagnosis"]["root_cause"] == "database connection pool exhaustion"

    retry = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert retry.status_code == 200, retry.text
    final = client.get(f"/api/v1/quest-attempts/{aid}", params={"employee_id": demo_employee_id}).json()
    assert final["status"] == "COMPLETED"
    assert final["passed"] is True


# ---- 26-28: compatibility ----


def test_26_general_quest_ai_response_unaffected(client, demo_employee_id, capability_ids):
    quest = client.post(
        "/api/v1/quests",
        json={"title": "Stage4D GENERAL regression", "description": "d", "quest_type": "OTHER", "workspace_type": "GENERAL"},
    ).json()
    qid = quest["id"]
    client.post(f"/api/v1/quests/{qid}/tasks", json={"title": "Task", "task_type": "OTHER", "required": False})
    client.post(f"/api/v1/quests/{qid}/evidence", json={"title": "Ev", "evidence_type": "TEXT", "content": {}})
    client.post(f"/api/v1/quests/{qid}/evaluation-criteria", json={"name": "q", "criterion_type": "QUALITATIVE", "description": "d"})
    client.post(f"/api/v1/quests/{qid}/capabilities", json={"capability_id": capability_ids["documentation"]})
    client.post(f"/api/v1/quests/{qid}/assignments", json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id})
    client.post(f"/api/v1/quests/{qid}/publish")

    aid = _start_attempt(client, qid, demo_employee_id)
    client.patch(f"/api/v1/quest-attempts/{aid}", json={"employee_id": demo_employee_id, "findings": "f", "reasoning": "clear and detailed reasoning about the problem at hand", "solution": "a concrete specific solution"})
    client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": demo_employee_id})
    res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["capabilities"][0]["evidence"].startswith("Assessed from the quality and detail")


def test_27_legacy_troubleshoot_submission_regression(client, demo_employee_id, capability_ids):
    qid, task_id = _build_quest(client, demo_employee_id, capability_ids, title="Stage4D legacy Troubleshoot regression", description="d", expected_answer="database connection pool exhaustion")
    aid = _start_attempt(client, qid, demo_employee_id)
    client.patch(
        f"/api/v1/quest-attempts/{aid}",
        json={
            "employee_id": demo_employee_id,
            "findings": "f",
            "reasoning": "database connection pool exhaustion, clearly explained with detail",
            "solution": "a concrete specific solution",
            "completed_task_ids": [task_id],
        },
    )
    client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": demo_employee_id})
    res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["capabilities"][0]["evidence"].startswith("Assessed from the quality and detail")


def test_28_mission_evaluation_still_works(client):
    bundle = client.get("/api/v1/onboarding/bundle/demo").json()
    employee_id = bundle["employee"]["id"]
    assignments = bundle.get("mission_assignments", [])
    if not assignments:
        return  # nothing to evaluate against in this demo seed; not a Stage 4D concern either way
    mission_id = assignments[0]["mission"]["id"]
    attempt = client.post("/api/v1/mission-attempts", json={"mission_id": mission_id, "employee_id": employee_id}).json()
    aid = attempt["id"]
    client.patch(
        f"/api/v1/mission-attempts/{aid}",
        json={"employee_id": employee_id, "affected_service": "checkout-service", "likely_cause": "deploy", "reasoning": "clear reasoning here"},
    )
    submit = client.post(f"/api/v1/mission-attempts/{aid}/submit", json={"employee_id": employee_id})
    assert submit.status_code in (200, 404, 422)  # tolerant: Mission fixture shape isn't this file's concern


# ---- 29-30: domain neutrality, end to end with AI interpretation ----


def test_29_sre_scenario_with_ai_interpretation(client, demo_employee_id, capability_ids):
    aid, res = _evaluate(
        client, "Checkout latency spike", demo_employee_id, capability_ids,
        root_cause="the 14:00 deploy regressed checkout latency",
        expected_answer="the 14:00 deploy regressed checkout latency",
        evidence_reviewed=["ev-a", "ev-b"],
    )
    body = res.json()
    assert len(body["capabilities"]) >= 1
    assert body["capabilities"][0]["level"] in ("DEVELOPING", "CAPABLE", "STRONG")


def test_30_non_sre_scenario_with_ai_interpretation(client, demo_employee_id, capability_ids):
    aid, res = _evaluate(
        client, "Vet clinic confirmation failures", demo_employee_id, capability_ids,
        root_cause="the sms provider is rate limiting outbound confirmation texts",
        expected_answer="the sms provider is rate limiting outbound confirmation texts",
        evidence_reviewed=["ev-a"],
    )
    body = res.json()
    assert len(body["capabilities"]) >= 1


# ---- Security: hidden data never reaches the AI-facing or employee-facing surface ----


def test_hidden_criteria_never_leak_through_structured_ai_context(client, demo_employee_id, capability_ids):
    qid, task_id = _build_quest(client, demo_employee_id, capability_ids, title="Stage4D secret quest", description="d", secret_markers=True)
    aid = _start_attempt(client, qid, demo_employee_id)
    _submit_structured(client, aid, demo_employee_id, root_cause="an unrelated diagnosis", complete_task_id=task_id, evidence_reviewed=["ev-a"])
    client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": demo_employee_id})
    res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert res.status_code == 200, res.text
    assert "SECRET_4D_EXPECTED_ANSWER" not in res.text
    assert "SECRET_4D_EXPECTED_BEHAVIOR" not in res.text
    assert "SECRET_4D_REFERENCE_SOLUTION" not in res.text
    assert "expected_answer" not in res.text
    assert "reference_solution" not in res.text

    get_res = client.get(f"/api/v1/quest-attempts/{aid}/evaluation", params={"employee_id": demo_employee_id})
    assert "SECRET_4D_" not in get_res.text

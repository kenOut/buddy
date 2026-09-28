"""Phase 3B Stage 5 backend tests: the Quest evaluation pipeline —
deterministic evaluation, AI interpretation, CapabilityEvaluation/
Evidence/Profile, lifecycle, security, idempotency, and concurrency.

Runs against an isolated SQLite file, deleted and recreated each run —
same convention as the other test_quest_*.py modules.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_quest_evaluation.db"
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
def demo_bundle(client):
    return client.get("/api/v1/onboarding/bundle/demo").json()


@pytest.fixture(scope="module")
def demo_employee_id(demo_bundle):
    return demo_bundle["employee"]["id"]


@pytest.fixture(scope="module")
def other_employee_id(client, demo_bundle):
    org_id = demo_bundle["employee"]["organization_id"]
    dept_id = demo_bundle["employee"]["department_id"]
    res = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": dept_id,
            "full_name": "Evaluation Outsider",
            "email": "evaluation-outsider@buddy.dev",
            "start_date": "2026-01-01",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


@pytest.fixture(scope="module")
def capability_ids(client):
    caps = client.get("/api/v1/capabilities").json()
    return {c["key"]: c["id"] for c in caps}


def _build_and_publish_quest(
    client,
    employee_id,
    capability_ids,
    *,
    title="Evaluation test quest",
    quest_type="INVESTIGATE",
    workspace_type="INVESTIGATION",
    expected_answer="checkout-service",
    map_capabilities=True,
):
    quest = client.post(
        "/api/v1/quests",
        json={
            "title": title,
            "description": "A real workplace problem for evaluation tests.",
            "quest_type": quest_type,
            "workspace_type": workspace_type,
        },
    ).json()
    qid = quest["id"]

    # Phase 6B: publishing an INVESTIGATE quest also requires an
    # INVESTIGATE-typed task and at least one evidence item.
    client.post(
        f"/api/v1/quests/{qid}/tasks",
        json={"title": "Identify the affected service", "task_type": "INVESTIGATE", "required": False},
    )
    client.post(
        f"/api/v1/quests/{qid}/evidence",
        json={"title": "Latency metrics", "evidence_type": "METRICS", "content": {}},
    )

    client.post(
        f"/api/v1/quests/{qid}/evaluation-criteria",
        json={
            "name": "Correct affected service",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": expected_answer,
            "max_score": 50,
        },
    )
    client.post(
        f"/api/v1/quests/{qid}/evaluation-criteria",
        json={
            "name": "Reasoning quality",
            "criterion_type": "QUALITATIVE",
            "description": "Is the explanation clear and well-supported?",
            "max_score": 50,
        },
    )

    if map_capabilities:
        client.post(
            f"/api/v1/quests/{qid}/capabilities",
            json={"capability_id": capability_ids["troubleshooting"], "weight": 1.0},
        )
        client.post(
            f"/api/v1/quests/{qid}/capabilities",
            json={"capability_id": capability_ids["documentation"], "weight": 0.5},
        )

    client.post(
        f"/api/v1/quests/{qid}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee_id},
    )

    if map_capabilities:
        pub = client.post(f"/api/v1/quests/{qid}/publish")
        assert pub.status_code == 200, pub.text
    else:
        # Stage 6A: the publish endpoint now requires >=1 mapped
        # capability, so this "published quest with zero capability
        # mappings" state can no longer be reached through normal usage
        # (and, once published, mappings can't be removed either — see
        # the immutability tests). It's still a real defensive path in
        # quest_evaluation_service.py worth covering (e.g. legacy data
        # from before this rule existed), so it's reached here by
        # setting status directly rather than via POST /publish.
        import asyncio

        from app.db.session import AsyncSessionLocal
        from app.models import Quest

        async def force_published():
            async with AsyncSessionLocal() as db:
                quest_obj = await db.get(Quest, qid)
                quest_obj.status = "PUBLISHED"
                await db.commit()

        asyncio.run(force_published())

    return qid


def _submit_ready_attempt(client, quest_id, employee_id, *, solution_text="checkout-service is the affected service."):
    attempt = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest_id, "employee_id": employee_id}
    ).json()
    aid = attempt["id"]
    client.patch(
        f"/api/v1/quest-attempts/{aid}",
        json={
            "employee_id": employee_id,
            "findings": "Latency spiked sharply on the relevant service.",
            "reasoning": "The timing lines up with a recent deploy that introduced a slow query, saturating the pool.",
            "solution": solution_text,
        },
    )
    submit = client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": employee_id})
    assert submit.status_code == 200, submit.text
    return aid


# =====================================================================
# Quest evaluation
# =====================================================================


def test_submitted_quest_can_be_evaluated(client, demo_employee_id, capability_ids):
    qid = _build_and_publish_quest(client, demo_employee_id, capability_ids, title="Evaluate a submitted quest")
    aid = _submit_ready_attempt(client, qid, demo_employee_id)

    res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "COMPLETED"
    assert len(body["capabilities"]) == 2


def test_correct_deterministic_criterion_passes(client, demo_employee_id, capability_ids):
    qid = _build_and_publish_quest(
        client, demo_employee_id, capability_ids, title="Correct deterministic", expected_answer="checkout-service"
    )
    aid = _submit_ready_attempt(client, qid, demo_employee_id, solution_text="checkout-service needs a rollback.")
    res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert res.status_code == 200
    final = client.get(f"/api/v1/quest-attempts/{aid}", params={"employee_id": demo_employee_id}).json()
    assert final["passed"] is True
    # Normalized across only the deterministically-checkable criteria (the
    # QUALITATIVE one contributes nothing to this score) -- 1/1 passed = 100%.
    assert final["score"] == 100.0


def test_incorrect_deterministic_criterion_fails(client, demo_employee_id, capability_ids):
    qid = _build_and_publish_quest(
        client, demo_employee_id, capability_ids, title="Incorrect deterministic", expected_answer="checkout-service"
    )
    aid = _submit_ready_attempt(client, qid, demo_employee_id, solution_text="payments-service is unrelated.")
    res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert res.status_code == 200
    final = client.get(f"/api/v1/quest-attempts/{aid}", params={"employee_id": demo_employee_id}).json()
    assert final["passed"] is False
    assert final["score"] == 0.0


def test_qualitative_criterion_reaches_ai_layer(client, demo_employee_id, capability_ids):
    """A QUALITATIVE criterion contributes nothing to the deterministic
    score, but its description is passed to the AI context (proven
    indirectly: the mock AI still produces capability assessments even
    though the only deterministic criterion is absent here)."""
    quest = client.post(
        "/api/v1/quests",
        json={
            "title": "Only qualitative criteria",
            "description": "A real workplace design problem.",
            "quest_type": "DESIGN",
            "workspace_type": "DESIGN",
        },
    ).json()
    qid = quest["id"]
    client.post(
        f"/api/v1/quests/{qid}/tasks",
        json={"title": "Design the mitigation approach", "task_type": "DESIGN", "required": False},
    )
    client.post(
        f"/api/v1/quests/{qid}/evaluation-criteria",
        json={"name": "Design clarity", "criterion_type": "QUALITATIVE", "description": "Is the design well-reasoned?"},
    )
    client.post(
        f"/api/v1/quests/{qid}/capabilities", json={"capability_id": capability_ids["problem_solving"]}
    )
    client.post(
        f"/api/v1/quests/{qid}/assignments", json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id}
    )
    client.post(f"/api/v1/quests/{qid}/publish")
    aid = _submit_ready_attempt(client, qid, demo_employee_id)

    res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert res.status_code == 200, res.text
    body = res.json()
    # No deterministic criteria existed at all -> objective defaults to passed/100
    final = client.get(f"/api/v1/quest-attempts/{aid}", params={"employee_id": demo_employee_id}).json()
    assert final["passed"] is True
    assert final["score"] == 100.0
    assert len(body["capabilities"]) == 1
    assert body["capabilities"][0]["capability"] == "problem_solving"


def test_evaluation_result_stored_and_attempt_completed(client, demo_employee_id, capability_ids):
    qid = _build_and_publish_quest(client, demo_employee_id, capability_ids, title="Stored evaluation check")
    aid = _submit_ready_attempt(client, qid, demo_employee_id)
    client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})

    get_eval = client.get(f"/api/v1/quest-attempts/{aid}/evaluation", params={"employee_id": demo_employee_id})
    assert get_eval.status_code == 200
    assert get_eval.json() is not None
    assert get_eval.json()["status"] == "COMPLETED"

    attempt = client.get(f"/api/v1/quest-attempts/{aid}", params={"employee_id": demo_employee_id}).json()
    assert attempt["status"] == "COMPLETED"


# =====================================================================
# Failure / retry
# =====================================================================


def test_ai_failure_leaves_attempt_submitted_and_preserves_work(client, demo_employee_id, capability_ids):
    import app.services.quest_evaluation_service as qes_mod
    from app.services.ai_provider import AIProviderError

    qid = _build_and_publish_quest(client, demo_employee_id, capability_ids, title="AI failure test")
    aid = _submit_ready_attempt(client, qid, demo_employee_id, solution_text="my careful solution text here")

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
    assert attempt["submission"]["solution"] == "my careful solution text here"

    no_eval = client.get(f"/api/v1/quest-attempts/{aid}/evaluation", params={"employee_id": demo_employee_id})
    assert no_eval.json() is None


def test_retry_after_ai_failure_succeeds(client, demo_employee_id, capability_ids):
    import app.services.quest_evaluation_service as qes_mod
    from app.services.ai_provider import AIProviderError

    qid = _build_and_publish_quest(client, demo_employee_id, capability_ids, title="Retry after failure")
    aid = _submit_ready_attempt(client, qid, demo_employee_id)

    class BrokenProvider:
        model_name = "broken"

        async def generate_for_quest(self, context):
            raise AIProviderError("simulated outage")

    original = qes_mod.get_ai_provider
    qes_mod.get_ai_provider = lambda name: BrokenProvider()
    try:
        client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    finally:
        qes_mod.get_ai_provider = original

    retry = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert retry.status_code == 200, retry.text
    final = client.get(f"/api/v1/quest-attempts/{aid}", params={"employee_id": demo_employee_id}).json()
    assert final["status"] == "COMPLETED"


def test_malformed_ai_response_rejected_and_attempt_preserved(client, demo_employee_id, capability_ids):
    import app.services.quest_evaluation_service as qes_mod

    qid = _build_and_publish_quest(client, demo_employee_id, capability_ids, title="Malformed AI response")
    aid = _submit_ready_attempt(client, qid, demo_employee_id)

    class MalformedProvider:
        model_name = "malformed"

        async def generate_for_quest(self, context):
            return "not valid json {{{"

    original = qes_mod.get_ai_provider
    qes_mod.get_ai_provider = lambda name: MalformedProvider()
    try:
        res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
        assert res.status_code == 502, res.text
    finally:
        qes_mod.get_ai_provider = original

    attempt = client.get(f"/api/v1/quest-attempts/{aid}", params={"employee_id": demo_employee_id}).json()
    assert attempt["status"] == "SUBMITTED"


# =====================================================================
# Lifecycle enforcement
# =====================================================================


def test_cannot_evaluate_in_progress_attempt(client, demo_employee_id, capability_ids):
    qid = _build_and_publish_quest(client, demo_employee_id, capability_ids, title="Cannot evaluate in-progress")
    attempt = client.post("/api/v1/quest-attempts", json={"quest_id": qid, "employee_id": demo_employee_id}).json()
    client.patch(f"/api/v1/quest-attempts/{attempt['id']}", json={"employee_id": demo_employee_id, "findings": "wip"})

    res = client.post(f"/api/v1/quest-attempts/{attempt['id']}/evaluate", json={"employee_id": demo_employee_id})
    assert res.status_code == 409


def test_cannot_autosave_while_evaluating(client, demo_employee_id, capability_ids):
    """Simulates the EVALUATING window directly at the DB level, since the
    mock provider resolves too fast to observe it via real concurrency."""
    qid = _build_and_publish_quest(client, demo_employee_id, capability_ids, title="Cannot autosave while evaluating")
    aid = _submit_ready_attempt(client, qid, demo_employee_id)

    import asyncio

    from app.db.session import AsyncSessionLocal
    from app.models import QuestAttempt

    async def force_evaluating():
        async with AsyncSessionLocal() as db:
            attempt = await db.get(QuestAttempt, aid)
            attempt.status = "EVALUATING"
            await db.commit()

    asyncio.run(force_evaluating())

    res = client.patch(f"/api/v1/quest-attempts/{aid}", json={"employee_id": demo_employee_id, "findings": "edit attempt"})
    assert res.status_code == 409

    resubmit = client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": demo_employee_id})
    assert resubmit.status_code == 409


def test_completed_attempt_not_re_evaluated_as_new(client, demo_employee_id, capability_ids):
    qid = _build_and_publish_quest(client, demo_employee_id, capability_ids, title="No duplicate completion")
    aid = _submit_ready_attempt(client, qid, demo_employee_id)
    first = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id}).json()
    second = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id}).json()
    assert first["evaluated_at"] == second["evaluated_at"]


# =====================================================================
# Capability evidence / profile
# =====================================================================


def test_quest_attempt_creates_capability_evidence(client, demo_employee_id, capability_ids):
    qid = _build_and_publish_quest(client, demo_employee_id, capability_ids, title="Evidence creation check")
    aid = _submit_ready_attempt(client, qid, demo_employee_id)
    client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})

    evidence = client.get(f"/api/v1/employees/{demo_employee_id}/capabilities/evidence").json()
    quest_evidence = [e for e in evidence if e.get("quest_attempt_id") == aid]
    assert len(quest_evidence) > 0
    assert all(e["mission_attempt_id"] is None for e in quest_evidence)
    sources = {e["source"] for e in quest_evidence}
    assert "deterministic" in sources
    assert "ai" in sources


def test_capability_profile_updates_from_quest_evidence(client, demo_employee_id, capability_ids):
    qid = _build_and_publish_quest(client, demo_employee_id, capability_ids, title="Profile update check")
    aid = _submit_ready_attempt(client, qid, demo_employee_id)
    client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})

    profiles = client.get(f"/api/v1/employees/{demo_employee_id}/capabilities").json()
    touched = [p for p in profiles if p["capability"]["key"] in ("troubleshooting", "documentation") and p["evidence_count"] > 0]
    assert len(touched) == 2
    for p in touched:
        assert p["level"] != "NOT_OBSERVED"


def test_quest_evidence_does_not_collapse_across_distinct_attempts(client, demo_employee_id, other_employee_id, capability_ids):
    """Regression test for the capability_aggregation.py bug this stage
    fixed: grouping evidence by the raw mission_attempt_id column would
    put every quest-sourced evidence row in one bucket (since
    mission_attempt_id is always None for them), making "3 separate
    quest completions" look identical to "1 quest completion with 3
    evidence rows." Two distinct QuestAttempts (even for two different
    employees, to keep the quests independent) must be treated as two
    distinct attempts by the aggregator, not one."""
    qid_a = _build_and_publish_quest(client, demo_employee_id, capability_ids, title="Aggregation source A")
    aid_a = _submit_ready_attempt(client, qid_a, demo_employee_id)
    client.post(f"/api/v1/quest-attempts/{aid_a}/evaluate", json={"employee_id": demo_employee_id})

    qid_b = _build_and_publish_quest(client, demo_employee_id, capability_ids, title="Aggregation source B")
    aid_b = _submit_ready_attempt(client, qid_b, demo_employee_id)
    client.post(f"/api/v1/quest-attempts/{aid_b}/evaluate", json={"employee_id": demo_employee_id})

    evidence = client.get(
        f"/api/v1/employees/{demo_employee_id}/capabilities/evidence",
        params={"capability_id": capability_ids["troubleshooting"]},
    ).json()
    distinct_attempt_ids = {e["quest_attempt_id"] for e in evidence if e["quest_attempt_id"] is not None}
    assert aid_a in distinct_attempt_ids and aid_b in distinct_attempt_ids
    assert len(distinct_attempt_ids) >= 2

    # 2 distinct attempts with evidence -> aggregation should now consider
    # "repeated" evidence rules (CAPABLE/STRONG), not the single-attempt
    # DEVELOPING-only rule.
    profile = next(
        p
        for p in client.get(f"/api/v1/employees/{demo_employee_id}/capabilities").json()
        if p["capability"]["key"] == "troubleshooting"
    )
    assert profile["level"] in ("CAPABLE", "STRONG"), profile


# =====================================================================
# Security
# =====================================================================


def test_employee_cannot_evaluate_another_employees_attempt(client, demo_employee_id, other_employee_id, capability_ids):
    qid = _build_and_publish_quest(client, demo_employee_id, capability_ids, title="Cross-employee evaluate")
    aid = _submit_ready_attempt(client, qid, demo_employee_id)
    res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": other_employee_id})
    assert res.status_code == 403


def test_employee_cannot_retrieve_another_employees_evaluation(client, demo_employee_id, other_employee_id, capability_ids):
    qid = _build_and_publish_quest(client, demo_employee_id, capability_ids, title="Cross-employee get evaluation")
    aid = _submit_ready_attempt(client, qid, demo_employee_id)
    client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})

    res = client.get(f"/api/v1/quest-attempts/{aid}/evaluation", params={"employee_id": other_employee_id})
    assert res.status_code == 403


def test_hidden_criteria_never_appear_in_employee_evaluation_response(client, demo_employee_id, capability_ids):
    quest = client.post(
        "/api/v1/quests",
        json={
            "title": "Secret leak check",
            "description": "A real workplace fix problem.",
            "quest_type": "FIX",
            "workspace_type": "FIX",
        },
    ).json()
    qid = quest["id"]
    client.post(
        f"/api/v1/quests/{qid}/tasks",
        json={"title": "Apply the fix", "task_type": "FIX", "required": False},
    )
    client.post(
        f"/api/v1/quests/{qid}/evidence",
        json={"title": "Reproduction steps", "evidence_type": "LOGS", "content": {}},
    )
    client.post(
        f"/api/v1/quests/{qid}/evaluation-criteria",
        json={
            "name": "hidden",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "SECRET_STAGE5_EXPECTED_ANSWER",
            "expected_behavior": "SECRET_STAGE5_EXPECTED_BEHAVIOR",
            "reference_solution": "SECRET_STAGE5_REFERENCE_SOLUTION",
        },
    )
    client.post(f"/api/v1/quests/{qid}/capabilities", json={"capability_id": capability_ids["troubleshooting"]})
    client.post(f"/api/v1/quests/{qid}/assignments", json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id})
    client.post(f"/api/v1/quests/{qid}/publish")
    aid = _submit_ready_attempt(client, qid, demo_employee_id, solution_text="unrelated solution text")

    eval_res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert eval_res.status_code == 200
    assert "SECRET_STAGE5_EXPECTED_ANSWER" not in eval_res.text
    assert "SECRET_STAGE5_EXPECTED_BEHAVIOR" not in eval_res.text
    assert "SECRET_STAGE5_REFERENCE_SOLUTION" not in eval_res.text
    assert "reference_solution" not in eval_res.text
    assert "expected_answer" not in eval_res.text
    assert "expected_behavior" not in eval_res.text

    get_res = client.get(f"/api/v1/quest-attempts/{aid}/evaluation", params={"employee_id": demo_employee_id})
    assert "SECRET_STAGE5_EXPECTED_ANSWER" not in get_res.text
    assert "SECRET_STAGE5_REFERENCE_SOLUTION" not in get_res.text


# =====================================================================
# Idempotency
# =====================================================================


def test_repeated_evaluate_returns_existing_evaluation(client, demo_employee_id, capability_ids):
    qid = _build_and_publish_quest(client, demo_employee_id, capability_ids, title="Idempotent evaluate")
    aid = _submit_ready_attempt(client, qid, demo_employee_id)

    results = [
        client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id}).json()
        for _ in range(3)
    ]
    evaluated_ats = {r["evaluated_at"] for r in results}
    assert len(evaluated_ats) == 1


def test_repeated_evaluation_does_not_duplicate_evidence_or_profiles(client, demo_employee_id, capability_ids):
    qid = _build_and_publish_quest(client, demo_employee_id, capability_ids, title="No duplicate evidence")
    aid = _submit_ready_attempt(client, qid, demo_employee_id)

    for _ in range(3):
        client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})

    evidence = client.get(f"/api/v1/employees/{demo_employee_id}/capabilities/evidence").json()
    quest_evidence = [e for e in evidence if e.get("quest_attempt_id") == aid]
    # Exactly 2 deterministic (one per mapped capability) + 2 AI (one per
    # mapped capability) = 4, regardless of how many times evaluate was called.
    assert len(quest_evidence) == 4, len(quest_evidence)

    profiles = client.get(f"/api/v1/employees/{demo_employee_id}/capabilities").json()
    troubleshooting_profiles = [p for p in profiles if p["capability"]["key"] == "troubleshooting"]
    assert len(troubleshooting_profiles) == 1  # unique constraint guarantees this; confirm no duplicate rows


# =====================================================================
# Concurrency
# =====================================================================


def test_concurrent_evaluation_produces_exactly_one_capability_evaluation(client, demo_employee_id, capability_ids):
    qid = _build_and_publish_quest(client, demo_employee_id, capability_ids, title="Concurrent evaluate")
    aid = _submit_ready_attempt(client, qid, demo_employee_id)

    def evaluate():
        return client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: evaluate(), range(8)))

    assert all(r.status_code == 200 for r in responses), [r.status_code for r in responses]
    evaluated_ats = {r.json()["evaluated_at"] for r in responses}
    assert len(evaluated_ats) == 1

    import asyncio

    from sqlalchemy import func, select

    from app.db.session import AsyncSessionLocal
    from app.models import CapabilityEvaluation

    async def count_rows():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(func.count())
                .select_from(CapabilityEvaluation)
                .where(CapabilityEvaluation.quest_attempt_id == aid)
            )
            return result.scalar_one()

    row_count = asyncio.run(count_rows())
    assert row_count == 1, f"expected exactly 1 CapabilityEvaluation row, found {row_count}"


# =====================================================================
# No-capability-mapping edge case
# =====================================================================


def test_quest_with_no_capability_mapping_completes_without_ai_evidence(client, demo_employee_id, capability_ids):
    qid = _build_and_publish_quest(
        client, demo_employee_id, capability_ids, title="No capability mapping", map_capabilities=False
    )
    aid = _submit_ready_attempt(client, qid, demo_employee_id)

    res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": demo_employee_id})
    assert res.status_code == 200
    assert res.json() is None  # nothing to interpret -> null, not an error

    final = client.get(f"/api/v1/quest-attempts/{aid}", params={"employee_id": demo_employee_id}).json()
    assert final["status"] == "COMPLETED"


# =====================================================================
# Regression
# =====================================================================


def test_mission_capability_evidence_still_works(client):
    """Confirms the capability_service.py generalization didn't break
    Mission's existing mission_attempt_id-based evidence path."""
    bundle = client.get("/api/v1/onboarding/bundle/demo").json()
    employee_id = bundle["employee"]["id"]
    missions = client.get(f"/api/v1/employees/{employee_id}/missions").json()
    target = next(
        (m for m in missions if m["mission"]["title"] == "Diagnose the checkout latency spike"), None
    )
    assert target is not None, "seeded investigation mission not found"
    mission_id = target["mission"]["id"]

    create = client.post(
        "/api/v1/mission-attempts", json={"mission_id": mission_id, "employee_id": employee_id}
    )
    attempt = create.json()
    if attempt.get("status") != "completed":
        submit = client.post(
            f"/api/v1/mission-attempts/{attempt['id']}/submit",
            json={
                "employee_id": employee_id,
                "affected_service": "checkout-service",
                "likely_cause": "New deploy introduced a query that exhausts the DB connection pool",
                "reasoning": "Deploy timing lines up with pool exhaustion; CPU stayed flat.",
                "evidence_viewed": ["metrics:m1", "logs:l1"],
            },
        )
        assert submit.status_code == 200

    evidence = client.get(f"/api/v1/employees/{employee_id}/capabilities/evidence").json()
    mission_evidence = [e for e in evidence if e.get("mission_attempt_id") is not None]
    assert len(mission_evidence) > 0
    assert all(e["quest_attempt_id"] is None for e in mission_evidence)

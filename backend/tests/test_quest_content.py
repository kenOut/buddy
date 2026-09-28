"""Phase 3B Stage 2 backend tests: QuestTask, QuestEvidence,
QuestEvaluationCriterion, QuestCapability, and the employee/server data
boundary.

Runs against an isolated SQLite file, deleted and recreated each run —
same convention as test_quests.py / test_mission_attempts.py.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_quest_content.db"
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
    bundle = client.get("/api/v1/onboarding/bundle/demo").json()
    return bundle["employee"]["id"]


@pytest.fixture(scope="module")
def quest_a(client):
    return client.post(
        "/api/v1/quests",
        json={
            "title": "Quest A — content home",
            "description": "A real workplace problem for content tests.",
            "quest_type": "INVESTIGATE",
            "workspace_type": "INVESTIGATION",
        },
    ).json()


@pytest.fixture(scope="module")
def quest_b(client):
    # A second, unrelated quest — used exclusively for cross-quest-access checks.
    return client.post(
        "/api/v1/quests",
        json={"title": "Quest B — a different quest", "quest_type": "BUILD", "workspace_type": "BUILD"},
    ).json()


@pytest.fixture(scope="module")
def capability_ids(client):
    caps = client.get("/api/v1/capabilities").json()
    assert len(caps) >= 2, "expected the seeded capability taxonomy"
    return [c["id"] for c in caps]


# =====================================================================
# QuestTask
# =====================================================================


def test_create_task_returns_201(client, quest_a):
    res = client.post(
        f"/api/v1/quests/{quest_a['id']}/tasks",
        json={"title": "Review the evidence", "task_type": "INVESTIGATE", "sort_order": 1},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["quest_id"] == quest_a["id"]
    assert body["required"] is True  # default


def test_create_task_rejects_invalid_type(client, quest_a):
    res = client.post(
        f"/api/v1/quests/{quest_a['id']}/tasks", json={"title": "Bad type", "task_type": "NOT_REAL"}
    )
    assert res.status_code == 422


def test_create_task_unknown_quest_returns_404(client):
    res = client.post(
        "/api/v1/quests/does-not-exist/tasks", json={"title": "x", "task_type": "OTHER"}
    )
    assert res.status_code == 404


def test_list_tasks_ordered_by_sort_order(client, quest_a):
    client.post(
        f"/api/v1/quests/{quest_a['id']}/tasks",
        json={"title": "Third", "task_type": "EXPLAIN", "sort_order": 30},
    )
    client.post(
        f"/api/v1/quests/{quest_a['id']}/tasks",
        json={"title": "First-ish", "task_type": "ANALYZE", "sort_order": 5},
    )
    res = client.get(f"/api/v1/quests/{quest_a['id']}/tasks")
    assert res.status_code == 200
    sort_orders = [t["sort_order"] for t in res.json()]
    assert sort_orders == sorted(sort_orders)


def test_update_task_persists(client, quest_a):
    created = client.post(
        f"/api/v1/quests/{quest_a['id']}/tasks",
        json={"title": "Original", "task_type": "BUILD"},
    ).json()
    res = client.patch(
        f"/api/v1/quests/{quest_a['id']}/tasks/{created['id']}",
        json={"title": "Updated", "required": False},
    )
    assert res.status_code == 200, res.text
    assert res.json()["title"] == "Updated"
    assert res.json()["required"] is False


def test_delete_task(client, quest_a):
    created = client.post(
        f"/api/v1/quests/{quest_a['id']}/tasks", json={"title": "Delete me", "task_type": "OTHER"}
    ).json()
    res = client.delete(f"/api/v1/quests/{quest_a['id']}/tasks/{created['id']}")
    assert res.status_code == 204
    listed = client.get(f"/api/v1/quests/{quest_a['id']}/tasks").json()
    assert created["id"] not in [t["id"] for t in listed]


def test_task_cross_quest_access_returns_404(client, quest_a, quest_b):
    task_in_a = client.post(
        f"/api/v1/quests/{quest_a['id']}/tasks", json={"title": "Belongs to A", "task_type": "FIX"}
    ).json()

    # reading it through quest_b's URL must 404, not succeed
    res = client.patch(
        f"/api/v1/quests/{quest_b['id']}/tasks/{task_in_a['id']}", json={"title": "hijacked"}
    )
    assert res.status_code == 404

    res_delete = client.delete(f"/api/v1/quests/{quest_b['id']}/tasks/{task_in_a['id']}")
    assert res_delete.status_code == 404

    # it must still exist, untouched, under its real quest
    still_there = client.get(f"/api/v1/quests/{quest_a['id']}/tasks").json()
    assert any(t["id"] == task_in_a["id"] and t["title"] == "Belongs to A" for t in still_there)


# =====================================================================
# QuestEvidence
# =====================================================================


def test_create_evidence_returns_201(client, quest_a):
    res = client.post(
        f"/api/v1/quests/{quest_a['id']}/evidence",
        json={
            "title": "checkout-service p95 latency",
            "evidence_type": "METRICS",
            "content": {"detail": "420ms -> 2150ms"},
            "sort_order": 1,
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["content"] == {"detail": "420ms -> 2150ms"}


def test_create_evidence_rejects_invalid_type(client, quest_a):
    res = client.post(
        f"/api/v1/quests/{quest_a['id']}/evidence", json={"title": "Bad", "evidence_type": "NOT_REAL"}
    )
    assert res.status_code == 422


def test_create_evidence_unknown_quest_returns_404(client):
    res = client.post(
        "/api/v1/quests/does-not-exist/evidence", json={"title": "x", "evidence_type": "TEXT"}
    )
    assert res.status_code == 404


def test_list_evidence_ordered_by_sort_order(client, quest_a):
    client.post(
        f"/api/v1/quests/{quest_a['id']}/evidence",
        json={"title": "Later", "evidence_type": "LOGS", "sort_order": 50},
    )
    client.post(
        f"/api/v1/quests/{quest_a['id']}/evidence",
        json={"title": "Earlier", "evidence_type": "LOGS", "sort_order": 2},
    )
    res = client.get(f"/api/v1/quests/{quest_a['id']}/evidence")
    sort_orders = [e["sort_order"] for e in res.json()]
    assert sort_orders == sorted(sort_orders)


def test_update_evidence_persists(client, quest_a):
    created = client.post(
        f"/api/v1/quests/{quest_a['id']}/evidence",
        json={"title": "Original evidence", "evidence_type": "TEXT"},
    ).json()
    res = client.patch(
        f"/api/v1/quests/{quest_a['id']}/evidence/{created['id']}",
        json={"title": "Updated evidence", "content": {"note": "revised"}},
    )
    assert res.status_code == 200, res.text
    assert res.json()["title"] == "Updated evidence"
    assert res.json()["content"] == {"note": "revised"}


def test_delete_evidence(client, quest_a):
    created = client.post(
        f"/api/v1/quests/{quest_a['id']}/evidence",
        json={"title": "Delete me", "evidence_type": "OTHER"},
    ).json()
    res = client.delete(f"/api/v1/quests/{quest_a['id']}/evidence/{created['id']}")
    assert res.status_code == 204
    listed = client.get(f"/api/v1/quests/{quest_a['id']}/evidence").json()
    assert created["id"] not in [e["id"] for e in listed]


def test_evidence_cross_quest_access_returns_404(client, quest_a, quest_b):
    evidence_in_a = client.post(
        f"/api/v1/quests/{quest_a['id']}/evidence",
        json={"title": "Belongs to A", "evidence_type": "CODE"},
    ).json()

    res = client.patch(
        f"/api/v1/quests/{quest_b['id']}/evidence/{evidence_in_a['id']}", json={"title": "hijacked"}
    )
    assert res.status_code == 404

    res_delete = client.delete(f"/api/v1/quests/{quest_b['id']}/evidence/{evidence_in_a['id']}")
    assert res_delete.status_code == 404


# =====================================================================
# QuestEvaluationCriterion (server-only)
# =====================================================================


def test_create_criterion_returns_201(client, quest_a):
    res = client.post(
        f"/api/v1/quests/{quest_a['id']}/evaluation-criteria",
        json={
            "name": "Correct affected service",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "checkout-service",
            "max_score": 40,
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["expected_answer"] == "checkout-service"


def test_create_criterion_rejects_invalid_type(client, quest_a):
    res = client.post(
        f"/api/v1/quests/{quest_a['id']}/evaluation-criteria",
        json={"name": "Bad type", "criterion_type": "NOT_REAL"},
    )
    assert res.status_code == 422


def test_create_criterion_rejects_non_positive_max_score(client, quest_a):
    res = client.post(
        f"/api/v1/quests/{quest_a['id']}/evaluation-criteria",
        json={"name": "Bad score", "criterion_type": "QUALITATIVE", "max_score": 0},
    )
    assert res.status_code == 422


def test_create_criterion_unknown_quest_returns_404(client):
    res = client.post(
        "/api/v1/quests/does-not-exist/evaluation-criteria",
        json={"name": "x", "criterion_type": "QUALITATIVE"},
    )
    assert res.status_code == 404


def test_list_criteria_ordered_by_sort_order(client, quest_a):
    client.post(
        f"/api/v1/quests/{quest_a['id']}/evaluation-criteria",
        json={"name": "Later", "criterion_type": "QUALITATIVE", "sort_order": 40},
    )
    client.post(
        f"/api/v1/quests/{quest_a['id']}/evaluation-criteria",
        json={"name": "Earlier", "criterion_type": "QUALITATIVE", "sort_order": 3},
    )
    res = client.get(f"/api/v1/quests/{quest_a['id']}/evaluation-criteria")
    sort_orders = [c["sort_order"] for c in res.json()]
    assert sort_orders == sorted(sort_orders)


def test_update_criterion_persists(client, quest_a):
    created = client.post(
        f"/api/v1/quests/{quest_a['id']}/evaluation-criteria",
        json={"name": "Original", "criterion_type": "BEHAVIORAL"},
    ).json()
    res = client.patch(
        f"/api/v1/quests/{quest_a['id']}/evaluation-criteria/{created['id']}",
        json={"expected_behavior": "Identify the connection pool exhaustion.", "max_score": 60},
    )
    assert res.status_code == 200, res.text
    assert res.json()["expected_behavior"] == "Identify the connection pool exhaustion."
    assert res.json()["max_score"] == 60


def test_delete_criterion(client, quest_a):
    created = client.post(
        f"/api/v1/quests/{quest_a['id']}/evaluation-criteria",
        json={"name": "Delete me", "criterion_type": "QUALITATIVE"},
    ).json()
    res = client.delete(f"/api/v1/quests/{quest_a['id']}/evaluation-criteria/{created['id']}")
    assert res.status_code == 204
    listed = client.get(f"/api/v1/quests/{quest_a['id']}/evaluation-criteria").json()
    assert created["id"] not in [c["id"] for c in listed]


def test_criterion_cross_quest_access_returns_404(client, quest_a, quest_b):
    criterion_in_a = client.post(
        f"/api/v1/quests/{quest_a['id']}/evaluation-criteria",
        json={"name": "Belongs to A", "criterion_type": "DETERMINISTIC"},
    ).json()

    res = client.patch(
        f"/api/v1/quests/{quest_b['id']}/evaluation-criteria/{criterion_in_a['id']}",
        json={"name": "hijacked"},
    )
    assert res.status_code == 404

    res_delete = client.delete(
        f"/api/v1/quests/{quest_b['id']}/evaluation-criteria/{criterion_in_a['id']}"
    )
    assert res_delete.status_code == 404


# =====================================================================
# QuestCapability
# =====================================================================


def test_create_capability_mapping_returns_201(client, quest_a, capability_ids):
    res = client.post(
        f"/api/v1/quests/{quest_a['id']}/capabilities",
        json={"capability_id": capability_ids[0], "weight": 1.0},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["capability_id"] == capability_ids[0]
    assert body["capability"]["id"] == capability_ids[0]
    assert body["weight"] == 1.0


def test_create_capability_mapping_unknown_quest_returns_404(client, capability_ids):
    res = client.post(
        "/api/v1/quests/does-not-exist/capabilities", json={"capability_id": capability_ids[0]}
    )
    assert res.status_code == 404


def test_create_capability_mapping_unknown_capability_returns_404(client, quest_a):
    res = client.post(
        f"/api/v1/quests/{quest_a['id']}/capabilities", json={"capability_id": "does-not-exist"}
    )
    assert res.status_code == 404


def test_list_capability_mappings(client, quest_a, capability_ids):
    res = client.get(f"/api/v1/quests/{quest_a['id']}/capabilities")
    assert res.status_code == 200
    ids = [m["capability_id"] for m in res.json()]
    assert capability_ids[0] in ids


def test_duplicate_capability_mapping_rejected_sequentially(client, quest_a, capability_ids):
    # capability_ids[0] was already mapped to quest_a above.
    res = client.post(
        f"/api/v1/quests/{quest_a['id']}/capabilities", json={"capability_id": capability_ids[0]}
    )
    assert res.status_code == 409, res.text


def test_duplicate_capability_mapping_rejected_concurrently(client, quest_b, capability_ids):
    payload = {"capability_id": capability_ids[1]}

    def create():
        return client.post(f"/api/v1/quests/{quest_b['id']}/capabilities", json=payload)

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: create(), range(8)))

    statuses = sorted(res.status_code for res in responses)
    assert statuses.count(201) == 1, f"expected exactly one 201, got statuses {statuses}"
    assert all(s in (201, 409) for s in statuses), f"unexpected status code(s): {statuses}"

    listed = client.get(f"/api/v1/quests/{quest_b['id']}/capabilities").json()
    matching = [m for m in listed if m["capability_id"] == capability_ids[1]]
    assert len(matching) == 1, f"expected exactly one mapping row, found {len(matching)}"


def test_delete_capability_mapping(client, quest_a, capability_ids):
    # map a fresh capability, then remove it by capability_id
    res = client.post(
        f"/api/v1/quests/{quest_a['id']}/capabilities", json={"capability_id": capability_ids[1]}
    )
    assert res.status_code == 201, res.text

    delete_res = client.delete(f"/api/v1/quests/{quest_a['id']}/capabilities/{capability_ids[1]}")
    assert delete_res.status_code == 204

    listed = client.get(f"/api/v1/quests/{quest_a['id']}/capabilities").json()
    assert capability_ids[1] not in [m["capability_id"] for m in listed]


def test_delete_unknown_capability_mapping_returns_404(client, quest_a):
    res = client.delete(f"/api/v1/quests/{quest_a['id']}/capabilities/does-not-exist")
    assert res.status_code == 404


# =====================================================================
# Critical security test: employee-safe serialization never leaks
# evaluation data.
# =====================================================================


def test_employee_safe_schema_never_leaks_evaluation_data(client):
    """Backend-contract proof, not a frontend check: build a Quest with a
    criterion containing obvious secrets, serialize it through
    EmployeeQuestResponse (never through QuestDetailResponse /
    QuestEvaluationCriterionInternal), and assert the secrets cannot
    appear anywhere in that output — structurally, not by convention."""
    quest = client.post(
        "/api/v1/quests",
        json={
            "title": "Security test quest",
            "quest_type": "TROUBLESHOOT",
            "workspace_type": "FIX",
        },
    ).json()

    client.post(
        f"/api/v1/quests/{quest['id']}/tasks",
        json={"title": "Investigate", "task_type": "INVESTIGATE"},
    )
    client.post(
        f"/api/v1/quests/{quest['id']}/evidence",
        json={"title": "Some evidence", "evidence_type": "TEXT", "content": {"note": "visible ok"}},
    )
    criterion_res = client.post(
        f"/api/v1/quests/{quest['id']}/evaluation-criteria",
        json={
            "name": "Secret criterion",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "SECRET_EXPECTED_ANSWER",
            "expected_behavior": "SECRET_EXPECTED_BEHAVIOR",
            "reference_solution": "SECRET_REFERENCE_SOLUTION",
        },
    )
    assert criterion_res.status_code == 201, criterion_res.text

    # Sanity: the secrets ARE retrievable through the manager/server-only
    # surface — otherwise this test would trivially "pass" for the wrong
    # reason (nothing to leak).
    detail = client.get(f"/api/v1/quests/{quest['id']}/detail").json()
    detail_text = str(detail)
    assert "SECRET_EXPECTED_ANSWER" in detail_text
    assert "SECRET_EXPECTED_BEHAVIOR" in detail_text
    assert "SECRET_REFERENCE_SOLUTION" in detail_text

    # Now build the employee-safe representation directly from the ORM
    # object used by /detail, and serialize it through
    # EmployeeQuestResponse — the actual backend contract that will back
    # the future employee-facing route (Stage 4).
    import asyncio

    from app.db.session import AsyncSessionLocal
    from app.schemas.quest import EmployeeQuestResponse
    from app.services import quest_service

    async def build_employee_view():
        async with AsyncSessionLocal() as db:
            quest_obj = await quest_service.get_quest_with_content(db, quest["id"])
            return EmployeeQuestResponse.model_validate(quest_obj).model_dump_json()

    employee_json = asyncio.run(build_employee_view())

    assert "SECRET_EXPECTED_ANSWER" not in employee_json
    assert "SECRET_EXPECTED_BEHAVIOR" not in employee_json
    assert "SECRET_REFERENCE_SOLUTION" not in employee_json
    assert "evaluation_criteria" not in employee_json
    assert "expected_answer" not in employee_json
    assert "expected_behavior" not in employee_json
    assert "reference_solution" not in employee_json
    # but the legitimately employee-visible content IS present
    assert "Investigate" in employee_json
    assert "visible ok" in employee_json


# =====================================================================
# Database integrity: Quest deletion cascades to content, never to the
# shared Capability record.
# =====================================================================


def test_deleting_quest_cascades_to_all_content_but_preserves_capability(client, capability_ids):
    quest = client.post(
        "/api/v1/quests",
        json={"title": "Deletion cascade test", "quest_type": "ANALYZE", "workspace_type": "ANALYSIS"},
    ).json()

    task = client.post(
        f"/api/v1/quests/{quest['id']}/tasks", json={"title": "t", "task_type": "ANALYZE"}
    ).json()
    evidence = client.post(
        f"/api/v1/quests/{quest['id']}/evidence", json={"title": "e", "evidence_type": "TEXT"}
    ).json()
    criterion = client.post(
        f"/api/v1/quests/{quest['id']}/evaluation-criteria",
        json={"name": "c", "criterion_type": "QUALITATIVE"},
    ).json()
    mapping = client.post(
        f"/api/v1/quests/{quest['id']}/capabilities", json={"capability_id": capability_ids[0]}
    ).json()

    import asyncio

    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models import Capability, Quest, QuestCapability, QuestEvaluationCriterion, QuestEvidence, QuestTask

    async def delete_quest_and_check():
        async with AsyncSessionLocal() as db:
            quest_obj = await db.get(Quest, quest["id"])
            await db.delete(quest_obj)
            await db.commit()

        async with AsyncSessionLocal() as db:
            task_row = await db.get(QuestTask, task["id"])
            evidence_row = await db.get(QuestEvidence, evidence["id"])
            criterion_row = await db.get(QuestEvaluationCriterion, criterion["id"])
            mapping_row = await db.get(QuestCapability, mapping["id"])
            capability_row = await db.get(Capability, capability_ids[0])
            quest_row = await db.get(Quest, quest["id"])
            return task_row, evidence_row, criterion_row, mapping_row, capability_row, quest_row

    task_row, evidence_row, criterion_row, mapping_row, capability_row, quest_row = asyncio.run(
        delete_quest_and_check()
    )

    assert quest_row is None
    assert task_row is None, "QuestTask should be deleted when its Quest is deleted"
    assert evidence_row is None, "QuestEvidence should be deleted when its Quest is deleted"
    assert criterion_row is None, "QuestEvaluationCriterion should be deleted when its Quest is deleted"
    assert mapping_row is None, "QuestCapability mapping should be deleted when its Quest is deleted"
    assert capability_row is not None, "the shared Capability record must NOT be deleted"


# =====================================================================
# Regression: Stage 1 QuestAttempt behavior must remain intact.
# =====================================================================


def test_quest_attempt_uniqueness_still_intact(client, quest_a, demo_employee_id, capability_ids):
    # Stage 3: attempt creation now requires a PUBLISHED quest with a
    # matching active assignment. Stage 6A additionally requires at
    # least one mapped capability. Phase 6B additionally requires (for
    # this INVESTIGATE quest) an INVESTIGATE-typed task, evidence, and a
    # well-formed evaluation criterion — quest_a is never published
    # earlier in this module, so these are safe to add unconditionally.
    task_res = client.post(
        f"/api/v1/quests/{quest_a['id']}/tasks",
        json={"title": "Identify the affected service", "task_type": "INVESTIGATE"},
    )
    assert task_res.status_code == 201, task_res.text
    evidence_res = client.post(
        f"/api/v1/quests/{quest_a['id']}/evidence",
        json={"title": "Latency metrics", "evidence_type": "METRICS", "content": {}},
    )
    assert evidence_res.status_code == 201, evidence_res.text
    # quest_a is a module-scoped fixture reused by every CRUD test above,
    # some of which leave incomplete criteria behind (e.g. a criterion
    # with no expected_answer, created only to test the update endpoint).
    # Quest Quality Validation (Phase 6B) requires EVERY existing
    # criterion to be well-formed, not just one — so clear the leftovers
    # before adding the one well-formed criterion this test needs.
    for leftover in client.get(f"/api/v1/quests/{quest_a['id']}/evaluation-criteria").json():
        client.delete(f"/api/v1/quests/{quest_a['id']}/evaluation-criteria/{leftover['id']}")
    criterion_res = client.post(
        f"/api/v1/quests/{quest_a['id']}/evaluation-criteria",
        json={
            "name": "Identifies the affected service",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "checkout-service",
        },
    )
    assert criterion_res.status_code == 201, criterion_res.text
    cap_res = client.post(
        f"/api/v1/quests/{quest_a['id']}/capabilities",
        json={"capability_id": capability_ids[0]},
    )
    assert cap_res.status_code in (201, 409)
    assign_res = client.post(
        f"/api/v1/quests/{quest_a['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    assert assign_res.status_code in (201, 409)  # 409 if an earlier test already assigned this employee
    publish_res = client.post(f"/api/v1/quests/{quest_a['id']}/publish")
    assert publish_res.status_code == 200, publish_res.text

    payload = {"quest_id": quest_a["id"], "employee_id": demo_employee_id}
    first = client.post("/api/v1/quest-attempts", json=payload).json()
    second = client.post("/api/v1/quest-attempts", json=payload).json()
    assert first["id"] == second["id"]

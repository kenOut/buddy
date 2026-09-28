"""Phase 3B Stage 4 backend tests: employee Quest access, QuestAttempt
autosave/submission, ownership, and the employee-safe security boundary.

Runs against an isolated SQLite file, deleted and recreated each run —
same convention as the other test_quest_*.py modules.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_quest_workspace.db"
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
            "full_name": "Workspace Outsider",
            "email": "workspace-outsider@buddy.dev",
            "start_date": "2026-01-01",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _build_quest(client, employee_id, *, publish=True, num_required=1, num_optional=1, num_evidence=2):
    quest = client.post(
        "/api/v1/quests",
        json={
            "title": "Workspace test quest",
            "description": "A real workplace problem for workspace tests.",
            "quest_type": "INVESTIGATE",
            "workspace_type": "INVESTIGATION",
        },
    ).json()
    quest_id = quest["id"]

    required_ids = []
    for i in range(num_required):
        t = client.post(
            f"/api/v1/quests/{quest_id}/tasks",
            json={"title": f"Required task {i}", "task_type": "INVESTIGATE", "required": True, "sort_order": i},
        ).json()
        required_ids.append(t["id"])

    optional_ids = []
    for i in range(num_optional):
        t = client.post(
            f"/api/v1/quests/{quest_id}/tasks",
            # task_type is INVESTIGATE (not EXPLAIN) so that num_required=0
            # calls still satisfy Phase 6B's investigation-task quality
            # check via this optional task alone.
            json={"title": f"Optional task {i}", "task_type": "INVESTIGATE", "required": False, "sort_order": 100 + i},
        ).json()
        optional_ids.append(t["id"])

    for i in range(num_evidence):
        client.post(
            f"/api/v1/quests/{quest_id}/evidence",
            json={"title": f"Evidence {i}", "evidence_type": "TEXT", "content": {"note": f"item {i}"}, "sort_order": i},
        )

    # Phase 6B: publishing an INVESTIGATE quest also requires a
    # well-formed evaluation criterion (the tasks/evidence above already
    # satisfy the investigation-task/evidence requirements).
    client.post(
        f"/api/v1/quests/{quest_id}/evaluation-criteria",
        json={
            "name": "Identifies the affected service",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "checkout-service",
        },
    )

    caps = client.get("/api/v1/capabilities").json()
    client.post(f"/api/v1/quests/{quest_id}/capabilities", json={"capability_id": caps[0]["id"]})

    client.post(
        f"/api/v1/quests/{quest_id}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee_id},
    )
    if publish:
        client.post(f"/api/v1/quests/{quest_id}/publish")

    return quest_id, required_ids, optional_ids


def _start_attempt(client, quest_id, employee_id):
    return client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest_id, "employee_id": employee_id}
    ).json()


# =====================================================================
# Access
# =====================================================================


def test_published_and_assigned_employee_can_access(client, demo_employee_id):
    quest_id, _, _ = _build_quest(client, demo_employee_id)
    res = client.get(f"/api/v1/quests/{quest_id}/employee", params={"employee_id": demo_employee_id})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["id"] == quest_id
    assert len(body["tasks"]) == 2
    assert len(body["evidence"]) == 2


def test_published_and_unassigned_employee_cannot_access(client, demo_employee_id, other_employee_id):
    quest_id, _, _ = _build_quest(client, demo_employee_id)
    res = client.get(f"/api/v1/quests/{quest_id}/employee", params={"employee_id": other_employee_id})
    assert res.status_code == 403


def test_draft_quest_cannot_be_accessed(client, demo_employee_id):
    quest_id, _, _ = _build_quest(client, demo_employee_id, publish=False)
    res = client.get(f"/api/v1/quests/{quest_id}/employee", params={"employee_id": demo_employee_id})
    assert res.status_code == 403


def test_archived_quest_cannot_create_new_attempt(client, demo_employee_id):
    quest_id, _, _ = _build_quest(client, demo_employee_id)
    client.post(f"/api/v1/quests/{quest_id}/archive")
    res = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest_id, "employee_id": demo_employee_id}
    )
    assert res.status_code == 409


def test_cross_employee_attempt_get_rejected(client, demo_employee_id, other_employee_id):
    quest_id, _, _ = _build_quest(client, demo_employee_id)
    attempt = _start_attempt(client, quest_id, demo_employee_id)
    res = client.get(
        f"/api/v1/quest-attempts/{attempt['id']}", params={"employee_id": other_employee_id}
    )
    assert res.status_code == 403


def test_cross_employee_attempt_update_rejected(client, demo_employee_id, other_employee_id):
    quest_id, _, _ = _build_quest(client, demo_employee_id)
    attempt = _start_attempt(client, quest_id, demo_employee_id)
    res = client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": other_employee_id, "reasoning": "hijacked"},
    )
    assert res.status_code == 403

    # confirm nothing was actually written
    check = client.get(
        f"/api/v1/quest-attempts/{attempt['id']}", params={"employee_id": demo_employee_id}
    ).json()
    assert check["submission"].get("reasoning") != "hijacked"


# =====================================================================
# Attempt creation / idempotency / concurrency
# =====================================================================


def test_first_access_creates_one_attempt(client, demo_employee_id):
    quest_id, _, _ = _build_quest(client, demo_employee_id)
    attempt = _start_attempt(client, quest_id, demo_employee_id)
    assert attempt["status"] == "NOT_STARTED"
    assert attempt["submission"] == {}


def test_repeated_access_returns_same_attempt(client, demo_employee_id):
    quest_id, _, _ = _build_quest(client, demo_employee_id)
    first = _start_attempt(client, quest_id, demo_employee_id)
    second = _start_attempt(client, quest_id, demo_employee_id)
    third = _start_attempt(client, quest_id, demo_employee_id)
    assert first["id"] == second["id"] == third["id"]


def test_concurrent_attempt_creation_still_produces_one_row(client, demo_employee_id):
    quest_id, _, _ = _build_quest(client, demo_employee_id)
    payload = {"quest_id": quest_id, "employee_id": demo_employee_id}

    def create():
        return client.post("/api/v1/quest-attempts", json=payload)

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: create(), range(8)))

    ids = {res.json()["id"] for res in responses}
    assert len(ids) == 1


# =====================================================================
# Quest content via the employee-safe route
# =====================================================================


def test_employee_quest_response_includes_tasks_and_evidence(client, demo_employee_id):
    quest_id, required_ids, optional_ids = _build_quest(client, demo_employee_id, num_required=2, num_optional=1)
    res = client.get(f"/api/v1/quests/{quest_id}/employee", params={"employee_id": demo_employee_id}).json()
    task_ids = [t["id"] for t in res["tasks"]]
    assert set(required_ids + optional_ids) == set(task_ids)
    assert all("required" in t for t in res["tasks"])


def test_employee_quest_response_never_includes_evaluation_criteria(client, demo_employee_id):
    quest_id, _, _ = _build_quest(client, demo_employee_id, publish=False)
    client.post(
        f"/api/v1/quests/{quest_id}/evaluation-criteria",
        json={
            "name": "hidden",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "SECRET_WORKSPACE_LEAK_CHECK",
            "expected_behavior": "SECRET_BEHAVIOR_LEAK_CHECK",
            "reference_solution": "SECRET_SOLUTION_LEAK_CHECK",
        },
    )
    client.post(f"/api/v1/quests/{quest_id}/publish")

    res = client.get(f"/api/v1/quests/{quest_id}/employee", params={"employee_id": demo_employee_id})
    assert res.status_code == 200, res.text
    assert "SECRET_WORKSPACE_LEAK_CHECK" not in res.text
    assert "SECRET_BEHAVIOR_LEAK_CHECK" not in res.text
    assert "SECRET_SOLUTION_LEAK_CHECK" not in res.text
    assert "evaluation_criteria" not in res.text
    assert "expected_answer" not in res.text
    assert "expected_behavior" not in res.text
    assert "reference_solution" not in res.text


# =====================================================================
# Work / autosave
# =====================================================================


def test_autosave_persists_submission_data(client, demo_employee_id):
    quest_id, required_ids, _ = _build_quest(client, demo_employee_id)
    attempt = _start_attempt(client, quest_id, demo_employee_id)

    res = client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "findings": "Saw a spike", "reasoning": "Deploy-correlated"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "IN_PROGRESS"
    assert body["submission"]["findings"] == "Saw a spike"
    assert body["submission"]["reasoning"] == "Deploy-correlated"


def test_autosave_partial_update_does_not_clobber_other_fields(client, demo_employee_id):
    quest_id, _, _ = _build_quest(client, demo_employee_id)
    attempt = _start_attempt(client, quest_id, demo_employee_id)

    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "findings": "first"},
    )
    res = client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "reasoning": "second"},
    )
    body = res.json()
    assert body["submission"]["findings"] == "first"
    assert body["submission"]["reasoning"] == "second"


def test_autosave_task_completion_toggles_full_list(client, demo_employee_id):
    quest_id, required_ids, optional_ids = _build_quest(client, demo_employee_id, num_required=2)
    attempt = _start_attempt(client, quest_id, demo_employee_id)

    res1 = client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "completed_task_ids": [required_ids[0]]},
    )
    assert res1.json()["submission"]["completed_task_ids"] == [required_ids[0]]

    res2 = client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "completed_task_ids": [required_ids[0], required_ids[1]]},
    )
    assert set(res2.json()["submission"]["completed_task_ids"]) == set(required_ids)


def test_returning_employee_receives_previous_work(client, demo_employee_id):
    quest_id, _, _ = _build_quest(client, demo_employee_id)
    attempt = _start_attempt(client, quest_id, demo_employee_id)
    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "solution": "my proposed fix"},
    )

    # Simulate "leave and come back": re-fetch via the same get-or-create
    # entry point a fresh page load would use.
    resumed = _start_attempt(client, quest_id, demo_employee_id)
    assert resumed["id"] == attempt["id"]
    assert resumed["submission"]["solution"] == "my proposed fix"


def test_autosave_rejected_once_submitted(client, demo_employee_id):
    quest_id, required_ids, _ = _build_quest(client, demo_employee_id, num_required=0)
    attempt = _start_attempt(client, quest_id, demo_employee_id)
    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "solution": "done"},
    )
    client.post(f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": demo_employee_id})

    res = client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "solution": "trying to edit after submit"},
    )
    assert res.status_code == 409


# =====================================================================
# Required tasks
# =====================================================================


def test_incomplete_required_task_blocks_submission(client, demo_employee_id):
    quest_id, required_ids, optional_ids = _build_quest(client, demo_employee_id, num_required=1, num_optional=1)
    attempt = _start_attempt(client, quest_id, demo_employee_id)
    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "solution": "work done", "completed_task_ids": []},
    )
    res = client.post(f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": demo_employee_id})
    assert res.status_code == 422, res.text


def test_completed_required_tasks_allow_submission(client, demo_employee_id):
    quest_id, required_ids, optional_ids = _build_quest(client, demo_employee_id, num_required=1, num_optional=1)
    attempt = _start_attempt(client, quest_id, demo_employee_id)
    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "solution": "work done", "completed_task_ids": required_ids},
    )
    res = client.post(f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": demo_employee_id})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "SUBMITTED"


def test_optional_tasks_do_not_block_submission(client, demo_employee_id):
    quest_id, required_ids, optional_ids = _build_quest(client, demo_employee_id, num_required=1, num_optional=1)
    attempt = _start_attempt(client, quest_id, demo_employee_id)
    # complete only the required task, deliberately leave the optional one out
    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "reasoning": "work done", "completed_task_ids": required_ids},
    )
    res = client.post(f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": demo_employee_id})
    assert res.status_code == 200, res.text


# =====================================================================
# Submission
# =====================================================================


def test_submission_without_any_work_field_rejected(client, demo_employee_id):
    quest_id, required_ids, _ = _build_quest(client, demo_employee_id, num_required=0)
    attempt = _start_attempt(client, quest_id, demo_employee_id)
    res = client.post(f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": demo_employee_id})
    assert res.status_code == 422


def test_repeated_submission_handled_safely(client, demo_employee_id):
    quest_id, required_ids, _ = _build_quest(client, demo_employee_id, num_required=0)
    attempt = _start_attempt(client, quest_id, demo_employee_id)
    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "findings": "done"},
    )
    first = client.post(f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": demo_employee_id})
    assert first.status_code == 200
    second = client.post(f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": demo_employee_id})
    assert second.status_code == 409

    final = client.get(
        f"/api/v1/quest-attempts/{attempt['id']}", params={"employee_id": demo_employee_id}
    ).json()
    assert final["status"] == "SUBMITTED"


def test_submitted_attempt_cannot_be_corrupted_back_to_in_progress(client, demo_employee_id):
    quest_id, required_ids, _ = _build_quest(client, demo_employee_id, num_required=0)
    attempt = _start_attempt(client, quest_id, demo_employee_id)
    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "findings": "done"},
    )
    client.post(f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": demo_employee_id})

    # get-or-create must return the SAME (now-submitted) row, never reset it
    resumed = _start_attempt(client, quest_id, demo_employee_id)
    assert resumed["id"] == attempt["id"]
    assert resumed["status"] == "SUBMITTED"


def test_submitted_attempt_remains_readable(client, demo_employee_id):
    quest_id, required_ids, _ = _build_quest(client, demo_employee_id, num_required=0)
    attempt = _start_attempt(client, quest_id, demo_employee_id)
    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "solution": "final answer"},
    )
    client.post(f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": demo_employee_id})

    res = client.get(f"/api/v1/quest-attempts/{attempt['id']}", params={"employee_id": demo_employee_id})
    assert res.status_code == 200
    assert res.json()["submission"]["solution"] == "final answer"


def test_submission_cross_employee_rejected(client, demo_employee_id, other_employee_id):
    quest_id, required_ids, _ = _build_quest(client, demo_employee_id, num_required=0)
    attempt = _start_attempt(client, quest_id, demo_employee_id)
    res = client.post(
        f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": other_employee_id}
    )
    assert res.status_code == 403


def test_archived_quest_blocks_submission_even_with_existing_attempt(client, demo_employee_id):
    quest_id, required_ids, _ = _build_quest(client, demo_employee_id, num_required=0)
    attempt = _start_attempt(client, quest_id, demo_employee_id)
    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "findings": "done"},
    )
    client.post(f"/api/v1/quests/{quest_id}/archive")

    res = client.post(f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": demo_employee_id})
    assert res.status_code == 409


# =====================================================================
# Security: evaluation data never leaks through attempt endpoints either
# =====================================================================


def test_submit_rejection_does_not_leak_evaluation_data(client, demo_employee_id):
    quest_id, required_ids, optional_ids = _build_quest(client, demo_employee_id, num_required=1)
    client.post(
        f"/api/v1/quests/{quest_id}/evaluation-criteria",
        json={
            "name": "hidden",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "SECRET_SUBMIT_REJECTION_LEAK_CHECK",
        },
    )
    attempt = _start_attempt(client, quest_id, demo_employee_id)
    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "findings": "done", "completed_task_ids": []},
    )
    res = client.post(f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": demo_employee_id})
    assert res.status_code == 422
    assert "SECRET_SUBMIT_REJECTION_LEAK_CHECK" not in res.text


# =====================================================================
# Regression
# =====================================================================


def test_mission_flow_still_works(client):
    bundle = client.get("/api/v1/onboarding/bundle/demo").json()
    res = client.get(f"/api/v1/employees/{bundle['employee']['id']}/missions")
    assert res.status_code == 200


def test_capability_endpoints_still_work(client):
    res = client.get("/api/v1/capabilities")
    assert res.status_code == 200
    assert len(res.json()) == 6


def test_quest_publish_lifecycle_still_works(client, demo_employee_id):
    quest_id, _, _ = _build_quest(client, demo_employee_id, publish=False)
    res = client.post(f"/api/v1/quests/{quest_id}/publish")
    assert res.status_code == 200
    assert res.json()["status"] == "PUBLISHED"

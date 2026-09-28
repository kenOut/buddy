"""Phase 3B Stage 3 backend tests: QuestAssignment, publish/archive
lifecycle, eligibility resolution, and QuestAttempt access protection.

Runs against an isolated SQLite file, deleted and recreated each run —
same convention as the other test_quest_*.py modules.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_quest_assignments.db"
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
def demo_department_id(demo_bundle):
    return demo_bundle["employee"]["department_id"]


@pytest.fixture(scope="module")
def demo_role_id(demo_bundle):
    return demo_bundle["employee"]["role_id"]


@pytest.fixture(scope="module")
def other_employee_id(client, demo_department_id, demo_bundle):
    # A second employee in a DIFFERENT department/role from the demo
    # employee, so department/role assignment tests can prove they do
    # NOT accidentally match everyone.
    org_id = demo_bundle["employee"]["organization_id"]
    departments = client.get("/api/v1/departments").json()
    other_dept = next(d for d in departments if d["id"] != demo_department_id and d["organization_id"] == org_id)
    res = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": other_dept["id"],
            "role_id": None,
            "full_name": "Outsider Employee",
            "email": "outsider@buddy.dev",
            "start_date": "2026-01-01",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"], other_dept["id"]


def _quest_payload(**overrides):
    payload = {
        "title": "Assignment test quest",
        # Stage 6A: publishing now requires a non-empty challenge
        # (description). Defaulted here so every test in this file gets
        # a publishable quest without repeating this in each one.
        "description": "A real workplace problem for the employee to investigate.",
        "quest_type": "INVESTIGATE",
        "workspace_type": "INVESTIGATION",
    }
    payload.update(overrides)
    return payload


def _new_quest(client, **overrides):
    return client.post("/api/v1/quests", json=_quest_payload(**overrides)).json()


@pytest.fixture(scope="module")
def capability_id(client):
    # Stage 6A: publishing now also requires at least one mapped
    # capability. Every publish call below maps this one first.
    caps = client.get("/api/v1/capabilities").json()
    return caps[0]["id"]


def _map_capability(client, quest_id, capability_id):
    client.post(f"/api/v1/quests/{quest_id}/capabilities", json={"capability_id": capability_id})


def _make_content_publishable(client, quest_id):
    """Phase 6B: publishing an INVESTIGATE quest (this file's default
    quest_type) also requires an INVESTIGATE-typed task, an evidence
    item, and a well-formed evaluation criterion — see
    quest_quality_service. Safe to call more than once against the same
    quest (no uniqueness constraint on tasks/evidence/criteria)."""
    client.post(
        f"/api/v1/quests/{quest_id}/tasks",
        json={"title": "Identify the affected service", "task_type": "INVESTIGATE"},
    )
    client.post(
        f"/api/v1/quests/{quest_id}/evidence",
        json={"title": "Latency metrics", "evidence_type": "METRICS", "content": {}},
    )
    client.post(
        f"/api/v1/quests/{quest_id}/evaluation-criteria",
        json={
            "name": "Identifies the affected service",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "checkout-service",
        },
    )


# =====================================================================
# Assignment CRUD
# =====================================================================


def test_create_employee_assignment(client, demo_employee_id):
    quest = _new_quest(client, title="Employee assignment quest")
    res = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["assignment_type"] == "EMPLOYEE"
    assert body["employee_id"] == demo_employee_id
    assert body["department_id"] is None
    assert body["role_id"] is None
    assert body["active"] is True


def test_create_department_assignment(client, demo_department_id):
    quest = _new_quest(client, title="Department assignment quest")
    res = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "DEPARTMENT", "department_id": demo_department_id},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["assignment_type"] == "DEPARTMENT"
    assert body["department_id"] == demo_department_id


def test_create_role_assignment(client, demo_role_id):
    quest = _new_quest(client, title="Role assignment quest")
    res = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "ROLE", "role_id": demo_role_id},
    )
    assert res.status_code == 201, res.text
    assert res.json()["role_id"] == demo_role_id


def test_list_assignments(client, demo_employee_id):
    quest = _new_quest(client, title="List assignments quest")
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    res = client.get(f"/api/v1/quests/{quest['id']}/assignments")
    assert res.status_code == 200
    assert len(res.json()) == 1


def test_get_assignment(client, demo_employee_id):
    quest = _new_quest(client, title="Get assignment quest")
    created = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    ).json()
    res = client.get(f"/api/v1/quests/{quest['id']}/assignments/{created['id']}")
    assert res.status_code == 200
    assert res.json()["id"] == created["id"]


def test_update_assignment_toggles_active(client, demo_employee_id):
    quest = _new_quest(client, title="Update assignment quest")
    created = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    ).json()
    res = client.patch(
        f"/api/v1/quests/{quest['id']}/assignments/{created['id']}", json={"active": False}
    )
    assert res.status_code == 200, res.text
    assert res.json()["active"] is False


def test_delete_assignment(client, demo_employee_id):
    quest = _new_quest(client, title="Delete assignment quest")
    created = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    ).json()
    res = client.delete(f"/api/v1/quests/{quest['id']}/assignments/{created['id']}")
    assert res.status_code == 204
    listed = client.get(f"/api/v1/quests/{quest['id']}/assignments").json()
    assert created["id"] not in [a["id"] for a in listed]


# =====================================================================
# Validation
# =====================================================================


def test_employee_assignment_without_employee_id_rejected(client):
    quest = _new_quest(client, title="Bad employee assignment")
    res = client.post(
        f"/api/v1/quests/{quest['id']}/assignments", json={"assignment_type": "EMPLOYEE"}
    )
    assert res.status_code == 422


def test_department_assignment_without_department_id_rejected(client):
    quest = _new_quest(client, title="Bad department assignment")
    res = client.post(
        f"/api/v1/quests/{quest['id']}/assignments", json={"assignment_type": "DEPARTMENT"}
    )
    assert res.status_code == 422


def test_role_assignment_without_role_id_rejected(client):
    quest = _new_quest(client, title="Bad role assignment")
    res = client.post(f"/api/v1/quests/{quest['id']}/assignments", json={"assignment_type": "ROLE"})
    assert res.status_code == 422


def test_multiple_targets_rejected(client, demo_employee_id, demo_department_id):
    quest = _new_quest(client, title="Multiple targets")
    res = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={
            "assignment_type": "EMPLOYEE",
            "employee_id": demo_employee_id,
            "department_id": demo_department_id,
        },
    )
    assert res.status_code == 422


def test_no_target_rejected(client):
    quest = _new_quest(client, title="No target at all")
    # assignment_type omitted entirely AND no target -> missing required field
    res = client.post(f"/api/v1/quests/{quest['id']}/assignments", json={})
    assert res.status_code == 422


def test_invalid_assignment_type_rejected(client, demo_employee_id):
    quest = _new_quest(client, title="Invalid type")
    res = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "NOT_REAL", "employee_id": demo_employee_id},
    )
    assert res.status_code == 422


def test_mismatched_type_and_target_rejected(client, demo_department_id):
    quest = _new_quest(client, title="Mismatched type and target")
    # assignment_type says EMPLOYEE but only department_id is populated
    res = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "department_id": demo_department_id},
    )
    assert res.status_code == 422


# =====================================================================
# Uniqueness
# =====================================================================


def test_duplicate_employee_assignment_rejected(client, demo_employee_id):
    quest = _new_quest(client, title="Duplicate employee assignment")
    first = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    assert second.status_code == 409, second.text


def test_duplicate_department_assignment_rejected(client, demo_department_id):
    quest = _new_quest(client, title="Duplicate department assignment")
    first = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "DEPARTMENT", "department_id": demo_department_id},
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "DEPARTMENT", "department_id": demo_department_id},
    )
    assert second.status_code == 409, second.text


def test_duplicate_role_assignment_rejected(client, demo_role_id):
    quest = _new_quest(client, title="Duplicate role assignment")
    first = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "ROLE", "role_id": demo_role_id},
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "ROLE", "role_id": demo_role_id},
    )
    assert second.status_code == 409, second.text


def test_concurrent_duplicate_assignment_creation_results_in_one_row(client, demo_employee_id):
    quest = _new_quest(client, title="Concurrent duplicate assignment")
    payload = {"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id}

    def create():
        return client.post(f"/api/v1/quests/{quest['id']}/assignments", json=payload)

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: create(), range(8)))

    statuses = sorted(res.status_code for res in responses)
    assert statuses.count(201) == 1, f"expected exactly one 201, got {statuses}"
    assert all(s in (201, 409) for s in statuses)

    listed = client.get(f"/api/v1/quests/{quest['id']}/assignments").json()
    assert len(listed) == 1, f"expected exactly one assignment row, found {len(listed)}"


# =====================================================================
# Parent scoping
# =====================================================================


def test_assignment_cross_quest_access_returns_404(client, demo_employee_id):
    quest_a = _new_quest(client, title="Assignment owner quest")
    quest_b = _new_quest(client, title="A different quest entirely")

    assignment = client.post(
        f"/api/v1/quests/{quest_a['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    ).json()

    get_res = client.get(f"/api/v1/quests/{quest_b['id']}/assignments/{assignment['id']}")
    assert get_res.status_code == 404

    patch_res = client.patch(
        f"/api/v1/quests/{quest_b['id']}/assignments/{assignment['id']}", json={"active": False}
    )
    assert patch_res.status_code == 404

    delete_res = client.delete(f"/api/v1/quests/{quest_b['id']}/assignments/{assignment['id']}")
    assert delete_res.status_code == 404

    # it must still exist, untouched, under its real quest
    still_there = client.get(f"/api/v1/quests/{quest_a['id']}/assignments/{assignment['id']}")
    assert still_there.status_code == 200
    assert still_there.json()["active"] is True


# =====================================================================
# Publishing
# =====================================================================


def test_draft_quest_can_publish_with_active_assignment(client, capability_id, demo_employee_id):
    quest = _new_quest(client, title="Publishable draft")
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    res = client.post(f"/api/v1/quests/{quest['id']}/publish")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "PUBLISHED"


def test_draft_quest_cannot_publish_without_assignment(client, capability_id):
    quest = _new_quest(client, title="No assignment yet")
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    res = client.post(f"/api/v1/quests/{quest['id']}/publish")
    assert res.status_code == 409, res.text


def test_published_quest_cannot_publish_again(client, capability_id, demo_employee_id):
    quest = _new_quest(client, title="Already published")
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    first = client.post(f"/api/v1/quests/{quest['id']}/publish")
    assert first.status_code == 200
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    second = client.post(f"/api/v1/quests/{quest['id']}/publish")
    assert second.status_code == 409, second.text


def test_archived_quest_cannot_publish(client, capability_id, demo_employee_id):
    quest = _new_quest(client, title="Archived cannot republish")
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    client.post(f"/api/v1/quests/{quest['id']}/publish")
    client.post(f"/api/v1/quests/{quest['id']}/archive")
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    res = client.post(f"/api/v1/quests/{quest['id']}/publish")
    assert res.status_code == 409, res.text


def test_valid_archive_transition_works(client, capability_id, demo_employee_id):
    quest = _new_quest(client, title="Archive me properly")
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    client.post(f"/api/v1/quests/{quest['id']}/publish")
    res = client.post(f"/api/v1/quests/{quest['id']}/archive")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "ARCHIVED"


def test_invalid_archive_transition_rejected(client):
    quest = _new_quest(client, title="Cannot archive a draft")
    res = client.post(f"/api/v1/quests/{quest['id']}/archive")
    assert res.status_code == 409, res.text


# =====================================================================
# Eligibility
# =====================================================================


def test_eligibility_direct_employee_assignment(client, capability_id, demo_employee_id):
    quest = _new_quest(client, title="Eligibility: direct employee")
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.get(f"/api/v1/quests/{quest['id']}/eligibility/{demo_employee_id}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["eligible"] is True
    assert body["quest_status"] == "PUBLISHED"
    assert body["matching_assignment_types"] == ["EMPLOYEE"]


def test_eligibility_department_assignment(client, capability_id, demo_employee_id, demo_department_id):
    quest = _new_quest(client, title="Eligibility: department")
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "DEPARTMENT", "department_id": demo_department_id},
    )
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.get(f"/api/v1/quests/{quest['id']}/eligibility/{demo_employee_id}").json()
    assert res["eligible"] is True
    assert res["matching_assignment_types"] == ["DEPARTMENT"]


def test_eligibility_role_assignment(client, capability_id, demo_employee_id, demo_role_id):
    quest = _new_quest(client, title="Eligibility: role")
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "ROLE", "role_id": demo_role_id},
    )
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.get(f"/api/v1/quests/{quest['id']}/eligibility/{demo_employee_id}").json()
    assert res["eligible"] is True
    assert res["matching_assignment_types"] == ["ROLE"]


def test_eligibility_multiple_matching_assignments(client, capability_id, demo_employee_id, demo_department_id):
    quest = _new_quest(client, title="Eligibility: multiple matches")
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "DEPARTMENT", "department_id": demo_department_id},
    )
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.get(f"/api/v1/quests/{quest['id']}/eligibility/{demo_employee_id}").json()
    assert res["eligible"] is True
    assert set(res["matching_assignment_types"]) == {"EMPLOYEE", "DEPARTMENT"}


def test_eligibility_inactive_assignment_not_eligible(client, capability_id, demo_employee_id):
    quest = _new_quest(client, title="Eligibility: inactive assignment")
    assignment = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    ).json()
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    client.post(f"/api/v1/quests/{quest['id']}/publish")
    client.patch(
        f"/api/v1/quests/{quest['id']}/assignments/{assignment['id']}", json={"active": False}
    )

    res = client.get(f"/api/v1/quests/{quest['id']}/eligibility/{demo_employee_id}").json()
    assert res["eligible"] is False
    assert res["matching_assignment_types"] == []


def test_eligibility_no_assignment_not_eligible(client, capability_id, other_employee_id):
    employee_id, _ = other_employee_id
    # A different quest with no assignment for this employee at all,
    # published against someone else.
    quest = _new_quest(client, title="Eligibility: no assignment for this one")
    other_placeholder_res = client.get("/api/v1/employees")
    someone_else = next(
        e for e in other_placeholder_res.json() if e["id"] not in (employee_id,)
    )
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": someone_else["id"]},
    )
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.get(f"/api/v1/quests/{quest['id']}/eligibility/{employee_id}").json()
    assert res["eligible"] is False


def test_eligibility_draft_quest_not_eligible(client, demo_employee_id):
    quest = _new_quest(client, title="Eligibility: draft")
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    # never published
    res = client.get(f"/api/v1/quests/{quest['id']}/eligibility/{demo_employee_id}").json()
    assert res["eligible"] is False
    assert res["quest_status"] == "DRAFT"
    assert res["matching_assignment_types"] == []


def test_eligibility_archived_quest_not_eligible(client, capability_id, demo_employee_id):
    quest = _new_quest(client, title="Eligibility: archived")
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    client.post(f"/api/v1/quests/{quest['id']}/publish")
    client.post(f"/api/v1/quests/{quest['id']}/archive")

    res = client.get(f"/api/v1/quests/{quest['id']}/eligibility/{demo_employee_id}").json()
    assert res["eligible"] is False
    assert res["quest_status"] == "ARCHIVED"


def test_eligibility_unknown_quest_returns_404(client, demo_employee_id):
    res = client.get(f"/api/v1/quests/does-not-exist/eligibility/{demo_employee_id}")
    assert res.status_code == 404


def test_eligibility_unknown_employee_returns_404(client):
    quest = _new_quest(client, title="Eligibility: unknown employee")
    res = client.get(f"/api/v1/quests/{quest['id']}/eligibility/does-not-exist")
    assert res.status_code == 404


def test_eligibility_response_never_leaks_evaluation_data(client, capability_id, demo_employee_id):
    quest = _new_quest(client, title="Eligibility: no evaluation leakage")
    client.post(
        f"/api/v1/quests/{quest['id']}/evaluation-criteria",
        json={
            "name": "hidden",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "SECRET_ELIGIBILITY_LEAK_CHECK",
        },
    )
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.get(f"/api/v1/quests/{quest['id']}/eligibility/{demo_employee_id}")
    assert "SECRET_ELIGIBILITY_LEAK_CHECK" not in res.text
    assert set(res.json().keys()) == {"eligible", "quest_status", "matching_assignment_types"}


# =====================================================================
# Attempt protection
# =====================================================================


def test_attempt_creation_rejected_for_draft_quest(client, demo_employee_id):
    quest = _new_quest(client, title="Attempt protection: draft")
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    # never published
    res = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest["id"], "employee_id": demo_employee_id}
    )
    assert res.status_code == 409, res.text


def test_attempt_creation_rejected_for_unassigned_employee(client, capability_id, other_employee_id, demo_employee_id):
    employee_id, _ = other_employee_id
    quest = _new_quest(client, title="Attempt protection: unassigned")
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest["id"], "employee_id": employee_id}
    )
    assert res.status_code == 403, res.text


def test_attempt_creation_allowed_for_assigned_employee(client, capability_id, demo_employee_id):
    quest = _new_quest(client, title="Attempt protection: assigned")
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest["id"], "employee_id": demo_employee_id}
    )
    assert res.status_code == 201, res.text


def test_attempt_creation_rejected_for_archived_quest(client, capability_id, demo_employee_id):
    quest = _new_quest(client, title="Attempt protection: archived")
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    client.post(f"/api/v1/quests/{quest['id']}/publish")
    client.post(f"/api/v1/quests/{quest['id']}/archive")

    res = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest["id"], "employee_id": demo_employee_id}
    )
    assert res.status_code == 409, res.text


def test_attempt_rejection_does_not_leak_evaluation_data(client, capability_id, other_employee_id, demo_employee_id):
    employee_id, _ = other_employee_id
    quest = _new_quest(client, title="Attempt protection: no leakage")
    client.post(
        f"/api/v1/quests/{quest['id']}/evaluation-criteria",
        json={
            "name": "hidden",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "SECRET_ATTEMPT_REJECTION_LEAK_CHECK",
        },
    )
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    _map_capability(client, quest['id'], capability_id)
    _make_content_publishable(client, quest['id'])
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest["id"], "employee_id": employee_id}
    )
    assert res.status_code == 403
    assert "SECRET_ATTEMPT_REJECTION_LEAK_CHECK" not in res.text


# =====================================================================
# Database integrity: Quest deletion cascades to assignments.
# =====================================================================


def test_deleting_quest_cascades_to_assignments(client, demo_employee_id):
    quest = _new_quest(client, title="Deletion cascades assignments")
    assignment = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    ).json()

    import asyncio

    from app.db.session import AsyncSessionLocal
    from app.models import Quest, QuestAssignment

    async def delete_and_check():
        async with AsyncSessionLocal() as db:
            quest_obj = await db.get(Quest, quest["id"])
            await db.delete(quest_obj)
            await db.commit()
        async with AsyncSessionLocal() as db:
            return await db.get(QuestAssignment, assignment["id"])

    assignment_row = asyncio.run(delete_and_check())
    assert assignment_row is None, "QuestAssignment should be deleted when its Quest is deleted"


# =====================================================================
# Regression
# =====================================================================


def test_quest_content_endpoints_still_work(client):
    quest = _new_quest(client, title="Regression: content endpoints")
    task_res = client.post(
        f"/api/v1/quests/{quest['id']}/tasks", json={"title": "still works", "task_type": "OTHER"}
    )
    assert task_res.status_code == 201


def test_mission_flow_still_works(client):
    bundle = client.get("/api/v1/onboarding/bundle/demo").json()
    missions = client.get(f"/api/v1/employees/{bundle['employee']['id']}/missions")
    assert missions.status_code == 200


def test_capability_endpoints_still_work(client):
    res = client.get("/api/v1/capabilities")
    assert res.status_code == 200
    assert len(res.json()) == 6

"""Phase 8H-3 (launch-audit follow-up) backend tests: exposing
QuestAssignment.required — a column and a readiness_service read that
already existed — through the manager-facing create/update API for the
first time.

This file deliberately does NOT re-test readiness_service's own
predicate from scratch (test_readiness_service.py already covers that
exhaustively) or eligibility resolution (test_quest_assignments.py
covers that). It covers exactly what changed: the new `required` field
on QuestAssignmentCreate/QuestAssignmentUpdate/QuestAssignmentResponse,
that setting it has no side effects beyond the one row, and that
everything downstream (readiness, recommendation, capability
evaluation, workspace access, the employee-safe response) keeps reading
it exactly as before.

Runs against its own isolated SQLite file, same convention as the other
test_*.py modules.
"""

import itertools
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_quest_assignment_required.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402

_dept_counter = itertools.count()
_quest_counter = itertools.count()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/api/v1/admin/login", json={"password": get_settings().admin_password})
        yield c
    TEST_DB_PATH.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def demo_bundle(client):
    return client.get("/api/v1/onboarding/bundle/demo").json()


@pytest.fixture(scope="module")
def org_id(demo_bundle):
    return demo_bundle["employee"]["organization_id"]


@pytest.fixture(scope="module")
def demo_employee_id(demo_bundle):
    return demo_bundle["employee"]["id"]


@pytest.fixture(scope="module")
def capability_id(client):
    caps = client.get("/api/v1/capabilities").json()
    return caps[0]["id"]


@pytest.fixture
def department(client, org_id):
    return client.post(
        "/api/v1/departments",
        json={"organization_id": org_id, "name": f"Required Toggle Dept {next(_dept_counter)}"},
    ).json()


def _employee_in(client, org_id, department_id):
    return client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department_id,
            "full_name": "Required Toggle Employee",
            "email": f"required-toggle-{next(_dept_counter)}@kowri.test",
        },
    ).json()


@pytest.fixture
def employee(client, org_id, department):
    return _employee_in(client, org_id, department["id"])


def _new_quest(client, department_id=None, **overrides):
    payload = {
        "title": f"Required Toggle Quest {next(_quest_counter)}",
        "description": "A real workplace problem used only for required-toggle tests.",
        "quest_type": "INVESTIGATE",
        "workspace_type": "INVESTIGATION",
    }
    if department_id:
        payload["department_id"] = department_id
    payload.update(overrides)
    return client.post("/api/v1/quests", json=payload).json()


def _make_content_publishable(client, quest_id, capability_id, expected_answer="checkout-service"):
    # required=False — a required task would need QuestTaskList's own
    # completion step (untested here, out of scope for this file); the
    # tests below only need a publishable, submittable quest.
    client.post(
        f"/api/v1/quests/{quest_id}/tasks",
        json={"title": "Identify the affected service", "task_type": "INVESTIGATE", "required": False},
    )
    client.post(
        f"/api/v1/quests/{quest_id}/evidence",
        json={"title": "Latency metrics", "evidence_type": "METRICS", "content": {}},
    )
    client.post(
        f"/api/v1/quests/{quest_id}/evaluation-criteria",
        json={
            "name": "Correct affected service",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": expected_answer,
            "max_score": 100,
        },
    )
    client.post(f"/api/v1/quests/{quest_id}/capabilities", json={"capability_id": capability_id})


def _submit_and_evaluate(client, quest_id, employee_id, solution="checkout-service is affected."):
    attempt = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest_id, "employee_id": employee_id}
    ).json()
    aid = attempt["id"]
    client.patch(
        f"/api/v1/quest-attempts/{aid}",
        json={
            "employee_id": employee_id,
            "findings": "Latency spiked sharply.",
            "reasoning": "Lines up with a recent deploy.",
            "solution": solution,
        },
    )
    submit = client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": employee_id})
    assert submit.status_code == 200, submit.text
    evaluate = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": employee_id})
    return aid, evaluate


# =====================================================================
# 1/2 — create with required=false / required=true
# =====================================================================


def test_create_assignment_with_required_false(client, employee):
    quest = _new_quest(client)
    res = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee["id"], "required": False},
    )
    assert res.status_code == 201, res.text
    assert res.json()["required"] is False


def test_create_assignment_with_required_true(client, employee):
    quest = _new_quest(client)
    res = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee["id"], "required": True},
    )
    assert res.status_code == 201, res.text
    assert res.json()["required"] is True


# =====================================================================
# 7 — omitting `required` on create keeps it False
# =====================================================================


def test_create_assignment_without_required_field_defaults_false(client, employee):
    quest = _new_quest(client)
    res = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee["id"]},
    )
    assert res.status_code == 201, res.text
    assert res.json()["required"] is False


# =====================================================================
# 3/4 — PATCH toggles required in both directions
# =====================================================================


def test_patch_required_false_to_true(client, employee):
    quest = _new_quest(client)
    created = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee["id"]},
    ).json()
    assert created["required"] is False

    res = client.patch(
        f"/api/v1/quests/{quest['id']}/assignments/{created['id']}", json={"required": True}
    )
    assert res.status_code == 200, res.text
    assert res.json()["required"] is True

    # Persisted, not just echoed back.
    reread = client.get(f"/api/v1/quests/{quest['id']}/assignments/{created['id']}").json()
    assert reread["required"] is True


def test_patch_required_true_to_false(client, employee):
    quest = _new_quest(client)
    created = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee["id"], "required": True},
    ).json()

    res = client.patch(
        f"/api/v1/quests/{quest['id']}/assignments/{created['id']}", json={"required": False}
    )
    assert res.status_code == 200, res.text
    assert res.json()["required"] is False

    reread = client.get(f"/api/v1/quests/{quest['id']}/assignments/{created['id']}").json()
    assert reread["required"] is False


def test_patch_required_leaves_active_untouched(client, employee):
    """Setting `required` alone must not implicitly change `active` —
    the two are independent flags on the same row."""
    quest = _new_quest(client)
    created = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee["id"]},
    ).json()
    assert created["active"] is True

    res = client.patch(
        f"/api/v1/quests/{quest['id']}/assignments/{created['id']}", json={"required": True}
    )
    assert res.json()["active"] is True


# =====================================================================
# 6 — cross-quest (isolation) mutation rejected, mirrors
# test_quest_assignments.py's existing test_assignment_cross_quest_
# access_returns_404 exactly, extended to the new field.
# =====================================================================


def test_required_patch_scoped_to_the_correct_quest(client, employee):
    quest_a = _new_quest(client)
    quest_b = _new_quest(client)

    assignment = client.post(
        f"/api/v1/quests/{quest_a['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee["id"]},
    ).json()

    patch_res = client.patch(
        f"/api/v1/quests/{quest_b['id']}/assignments/{assignment['id']}", json={"required": True}
    )
    assert patch_res.status_code == 404

    # Untouched under its real quest.
    still_there = client.get(f"/api/v1/quests/{quest_a['id']}/assignments/{assignment['id']}").json()
    assert still_there["required"] is False


# =====================================================================
# 8 — remains required after the Quest is completed
# =====================================================================


def test_required_assignment_stays_required_after_quest_completion(
    client, employee, department, capability_id
):
    quest = _new_quest(client, department_id=department["id"])
    _make_content_publishable(client, quest["id"], capability_id)
    assignment = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee["id"], "required": True},
    ).json()
    publish = client.post(f"/api/v1/quests/{quest['id']}/publish")
    assert publish.status_code == 200, publish.text

    _submit_and_evaluate(client, quest["id"], employee["id"])

    reread = client.get(f"/api/v1/quests/{quest['id']}/assignments/{assignment['id']}").json()
    assert reread["required"] is True


# =====================================================================
# 9 — toggling required changes readiness only through the existing
# readiness_service read, nothing bespoke
# =====================================================================


def test_toggling_required_changes_readiness_summary(client, employee, department, capability_id):
    quest = _new_quest(client, department_id=department["id"])
    _make_content_publishable(client, quest["id"], capability_id)
    assignment = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee["id"]},
    ).json()
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    before = client.get(f"/api/v1/employees/{employee['id']}/readiness-summary").json()
    assert before["required_quest_count"] == 0

    client.patch(f"/api/v1/quests/{quest['id']}/assignments/{assignment['id']}", json={"required": True})
    after_true = client.get(f"/api/v1/employees/{employee['id']}/readiness-summary").json()
    assert after_true["required_quest_count"] == 1
    assert after_true["completed_required_quest_count"] == 0
    assert after_true["ready"] is False

    client.patch(f"/api/v1/quests/{quest['id']}/assignments/{assignment['id']}", json={"required": False})
    after_false = client.get(f"/api/v1/employees/{employee['id']}/readiness-summary").json()
    assert after_false["required_quest_count"] == 0


# =====================================================================
# 10 — required does not alter recommendation ranking
# =====================================================================


def test_required_flag_does_not_alter_next_quest_recommendation(
    client, employee, department, capability_id
):
    quest = _new_quest(client, department_id=department["id"])
    _make_content_publishable(client, quest["id"], capability_id)
    assignment = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee["id"]},
    ).json()
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    before = client.get(f"/api/v1/employees/{employee['id']}/next-quest")
    assert before.status_code == 200
    before_body = before.json()

    client.patch(f"/api/v1/quests/{quest['id']}/assignments/{assignment['id']}", json={"required": True})

    after = client.get(f"/api/v1/employees/{employee['id']}/next-quest")
    assert after.status_code == 200
    after_body = after.json()

    # Same recommendation shape/target either way — required-ness is not
    # a ranking input.
    assert before_body.get("quest", {}).get("id") == after_body.get("quest", {}).get("id")


# =====================================================================
# 11 — required does not alter capability evaluation
# =====================================================================


def test_required_flag_does_not_alter_capability_evaluation(
    client, employee, department, capability_id
):
    quest = _new_quest(client, department_id=department["id"])
    _make_content_publishable(client, quest["id"], capability_id)
    assignment = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee["id"]},
    ).json()
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    attempt_id, evaluate_res = _submit_and_evaluate(client, quest["id"], employee["id"])
    assert evaluate_res.status_code == 200
    before_eval = evaluate_res.json()

    client.patch(f"/api/v1/quests/{quest['id']}/assignments/{assignment['id']}", json={"required": True})

    reread_eval = client.get(
        f"/api/v1/quest-attempts/{attempt_id}/evaluation", params={"employee_id": employee["id"]}
    )
    assert reread_eval.status_code == 200
    after_eval = reread_eval.json()
    assert after_eval["summary"] == before_eval["summary"]
    assert after_eval["capabilities"] == before_eval["capabilities"]


# =====================================================================
# 12 — required alone never creates a workspace grant
# =====================================================================


def test_required_flag_alone_does_not_create_workspace_grant(
    client, employee, department, capability_id
):
    quest = _new_quest(client, department_id=department["id"])
    _make_content_publishable(client, quest["id"], capability_id)
    assignment = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee["id"]},
    ).json()
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    # A configured, active workspace integration exists for this
    # department — if the PATCH itself ever triggered a grant, this is
    # exactly the setup that would let it happen.
    client.post(
        f"/api/v1/departments/{department['id']}/workspace",
        json={
            "provider": "google_drive",
            "external_ref": "required-toggle-test-drive",
            "display_name": "Required Toggle Workspace",
            "workspace_link": "https://drive.google.com/drive/folders/required-toggle-test",
        },
    )

    res = client.patch(
        f"/api/v1/quests/{quest['id']}/assignments/{assignment['id']}", json={"required": True}
    )
    assert res.status_code == 200

    access = client.get(f"/api/v1/employees/{employee['id']}/workspace-access").json()
    assert access["status"] != "GRANTED"


# =====================================================================
# 13 — manager response includes `required`
# =====================================================================


def test_manager_response_includes_required_field(client, employee):
    quest = _new_quest(client)
    created = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee["id"], "required": True},
    ).json()
    assert "required" in created
    assert created["required"] is True

    listed = client.get(f"/api/v1/quests/{quest['id']}/assignments").json()
    assert all("required" in a for a in listed)


# =====================================================================
# 14 — employee-safe response still exposes only required_for_readiness
# =====================================================================


def test_employee_quest_response_exposes_only_required_for_readiness(
    client, employee, department, capability_id
):
    quest = _new_quest(client, department_id=department["id"])
    _make_content_publishable(client, quest["id"], capability_id)
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee["id"], "required": True},
    )
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.get(f"/api/v1/quests/{quest['id']}/employee", params={"employee_id": employee["id"]})
    assert res.status_code == 200
    body = res.json()
    assert body["required_for_readiness"] is True
    # No raw assignment object, no bare `required` key, no evaluation
    # criteria anywhere in the employee-facing payload.
    assert "required" not in body
    assert "assignments" not in body
    assert "evaluation_criteria" not in body


# =====================================================================
# Optional/deactivated/archived must never read as required_for_readiness
# =====================================================================


def test_optional_assignment_is_not_required_for_readiness(client, employee, department, capability_id):
    quest = _new_quest(client, department_id=department["id"])
    _make_content_publishable(client, quest["id"], capability_id)
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee["id"], "required": False},
    )
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.get(f"/api/v1/quests/{quest['id']}/employee", params={"employee_id": employee["id"]})
    assert res.json()["required_for_readiness"] is False


def test_deactivated_required_assignment_is_not_required_for_readiness(
    client, employee, department, capability_id
):
    quest = _new_quest(client, department_id=department["id"])
    _make_content_publishable(client, quest["id"], capability_id)
    assignment = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee["id"], "required": True},
    ).json()
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    client.patch(
        f"/api/v1/quests/{quest['id']}/assignments/{assignment['id']}", json={"active": False}
    )

    res = client.get(f"/api/v1/quests/{quest['id']}/employee", params={"employee_id": employee["id"]})
    # Deactivated -> no longer eligible at all, so the employee-safe
    # endpoint now correctly refuses access outright.
    assert res.status_code == 403


def test_archived_quest_required_assignment_summary_excludes_it(
    client, employee, department, capability_id
):
    quest = _new_quest(client, department_id=department["id"])
    _make_content_publishable(client, quest["id"], capability_id)
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee["id"], "required": True},
    )
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    before_archive = client.get(f"/api/v1/employees/{employee['id']}/readiness-summary").json()
    assert before_archive["required_quest_count"] == 1

    archive_res = client.post(f"/api/v1/quests/{quest['id']}/archive")
    assert archive_res.status_code == 200, archive_res.text

    after_archive = client.get(f"/api/v1/employees/{employee['id']}/readiness-summary").json()
    assert after_archive["required_quest_count"] == 0

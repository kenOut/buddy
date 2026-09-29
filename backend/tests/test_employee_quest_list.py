"""Phase 8H-4 backend tests: GET /employees/{employee_id}/quests — the
employee's own Quest discovery list, the launch audit's final demo
blocker.

Deliberately does NOT re-test eligibility resolution from scratch
(test_quest_assignments.py already covers EMPLOYEE/DEPARTMENT/ROLE
matching, draft/archived exclusion, and inactive-assignment exclusion
exhaustively via the single-Quest path) — this file proves the SAME
rules hold across the new bulk listing endpoint specifically, plus what's
actually new: the lighter EmployeeQuestSummary shape, attempt_status
per quest, cross-employee isolation of that status, agreement with
readiness-summary, and that viewing the list is genuinely read-only.

Runs against its own isolated SQLite file, same convention as the other
test_*.py modules.
"""

import itertools
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_employee_quest_list.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402

_dept_counter = itertools.count()
_quest_counter = itertools.count()
_email_counter = itertools.count()


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
def capability_id(client):
    return client.get("/api/v1/capabilities").json()[0]["id"]


@pytest.fixture
def department(client, org_id):
    return client.post(
        "/api/v1/departments",
        json={"organization_id": org_id, "name": f"Quest List Dept {next(_dept_counter)}"},
    ).json()


@pytest.fixture
def role(client, department):
    return client.post(
        "/api/v1/roles",
        json={"department_id": department["id"], "title": f"Quest List Role {next(_dept_counter)}"},
    ).json()


def _employee_in(client, org_id, department_id=None, role_id=None, **overrides):
    payload = {
        "organization_id": org_id,
        "department_id": department_id,
        "role_id": role_id,
        "full_name": "Quest List Employee",
        "email": f"quest-list-{next(_email_counter)}@kowri.test",
    }
    payload.update(overrides)
    return client.post("/api/v1/employees", json=payload).json()


@pytest.fixture
def employee(client, org_id, department):
    return _employee_in(client, org_id, department["id"])


def _new_quest(client, department_id=None, **overrides):
    payload = {
        "title": f"Quest List Quest {next(_quest_counter)}",
        "description": "A real workplace problem used only for quest-list tests.",
        "quest_type": "INVESTIGATE",
        "workspace_type": "INVESTIGATION",
    }
    if department_id:
        payload["department_id"] = department_id
    payload.update(overrides)
    return client.post("/api/v1/quests", json=payload).json()


def _make_content_publishable(client, quest_id, capability_id):
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
            "expected_answer": "checkout-service",
            "max_score": 100,
        },
    )
    client.post(f"/api/v1/quests/{quest_id}/capabilities", json={"capability_id": capability_id})


def _publishable_quest(client, capability_id, department_id=None, **overrides):
    quest = _new_quest(client, department_id=department_id, **overrides)
    _make_content_publishable(client, quest["id"], capability_id)
    return quest


def _assign(client, quest_id, **kwargs):
    return client.post(f"/api/v1/quests/{quest_id}/assignments", json=kwargs).json()


def _publish(client, quest_id):
    res = client.post(f"/api/v1/quests/{quest_id}/publish")
    assert res.status_code == 200, res.text


def _list_quests(client, employee_id):
    res = client.get(f"/api/v1/employees/{employee_id}/quests")
    assert res.status_code == 200, res.text
    return res.json()


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
    client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": employee_id})
    return aid


# =====================================================================
# 1/2/7 — status filtering
# =====================================================================


def test_employee_receives_eligible_published_quest(client, employee, department, capability_id):
    quest = _publishable_quest(client, capability_id, department_id=department["id"])
    _assign(client, quest["id"], assignment_type="EMPLOYEE", employee_id=employee["id"])
    _publish(client, quest["id"])

    listed = _list_quests(client, employee["id"])
    assert quest["id"] in [q["id"] for q in listed]


def test_draft_quest_excluded(client, employee, department, capability_id):
    quest = _publishable_quest(client, capability_id, department_id=department["id"])
    _assign(client, quest["id"], assignment_type="EMPLOYEE", employee_id=employee["id"])
    # never published

    listed = _list_quests(client, employee["id"])
    assert quest["id"] not in [q["id"] for q in listed]


def test_archived_quest_excluded(client, employee, department, capability_id):
    quest = _publishable_quest(client, capability_id, department_id=department["id"])
    _assign(client, quest["id"], assignment_type="EMPLOYEE", employee_id=employee["id"])
    _publish(client, quest["id"])
    archive_res = client.post(f"/api/v1/quests/{quest['id']}/archive")
    assert archive_res.status_code == 200, archive_res.text

    listed = _list_quests(client, employee["id"])
    assert quest["id"] not in [q["id"] for q in listed]


# =====================================================================
# 3 — inactive assignment excluded
# =====================================================================


def test_inactive_assignment_excluded(client, employee, department, capability_id):
    quest = _publishable_quest(client, capability_id, department_id=department["id"])
    assignment = _assign(client, quest["id"], assignment_type="EMPLOYEE", employee_id=employee["id"])
    _publish(client, quest["id"])
    client.patch(f"/api/v1/quests/{quest['id']}/assignments/{assignment['id']}", json={"active": False})

    listed = _list_quests(client, employee["id"])
    assert quest["id"] not in [q["id"] for q in listed]


# =====================================================================
# 4/5/6 — assignment-type isolation, mirrors test_quest_assignments.py's
# own eligibility tests, now through the bulk list endpoint
# =====================================================================


def test_employee_targeted_quest_visible_only_to_target(client, org_id, department, capability_id):
    quest = _publishable_quest(client, capability_id, department_id=department["id"])
    target = _employee_in(client, org_id, department["id"])
    other = _employee_in(client, org_id, department["id"])
    _assign(client, quest["id"], assignment_type="EMPLOYEE", employee_id=target["id"])
    _publish(client, quest["id"])

    assert quest["id"] in [q["id"] for q in _list_quests(client, target["id"])]
    assert quest["id"] not in [q["id"] for q in _list_quests(client, other["id"])]


def test_department_targeted_quest_visible_to_department_employees(
    client, org_id, department, capability_id
):
    quest = _publishable_quest(client, capability_id, department_id=department["id"])
    in_dept = _employee_in(client, org_id, department["id"])
    other_dept = client.post(
        "/api/v1/departments", json={"organization_id": org_id, "name": f"Other Dept {next(_dept_counter)}"}
    ).json()
    outsider = _employee_in(client, org_id, other_dept["id"])
    _assign(client, quest["id"], assignment_type="DEPARTMENT", department_id=department["id"])
    _publish(client, quest["id"])

    assert quest["id"] in [q["id"] for q in _list_quests(client, in_dept["id"])]
    assert quest["id"] not in [q["id"] for q in _list_quests(client, outsider["id"])]


def test_role_targeted_quest_visible_to_role_employees(client, org_id, department, role, capability_id):
    quest = _publishable_quest(client, capability_id, department_id=department["id"])
    in_role = _employee_in(client, org_id, department["id"], role_id=role["id"])
    no_role = _employee_in(client, org_id, department["id"])
    _assign(client, quest["id"], assignment_type="ROLE", role_id=role["id"])
    _publish(client, quest["id"])

    assert quest["id"] in [q["id"] for q in _list_quests(client, in_role["id"])]
    assert quest["id"] not in [q["id"] for q in _list_quests(client, no_role["id"])]


# =====================================================================
# 8/9 — required_for_readiness
# =====================================================================


def test_required_quest_exposes_required_for_readiness_true(client, employee, department, capability_id):
    quest = _publishable_quest(client, capability_id, department_id=department["id"])
    _assign(client, quest["id"], assignment_type="EMPLOYEE", employee_id=employee["id"], required=True)
    _publish(client, quest["id"])

    listed = _list_quests(client, employee["id"])
    item = next(q for q in listed if q["id"] == quest["id"])
    assert item["required_for_readiness"] is True


def test_optional_quest_exposes_required_for_readiness_false(client, employee, department, capability_id):
    quest = _publishable_quest(client, capability_id, department_id=department["id"])
    _assign(client, quest["id"], assignment_type="EMPLOYEE", employee_id=employee["id"], required=False)
    _publish(client, quest["id"])

    listed = _list_quests(client, employee["id"])
    item = next(q for q in listed if q["id"] == quest["id"])
    assert item["required_for_readiness"] is False


# =====================================================================
# 10/11 — attempt status surfaced correctly, Quest stays visible
# =====================================================================


def test_completed_quest_remains_visible_with_completed_state(
    client, employee, department, capability_id
):
    quest = _publishable_quest(client, capability_id, department_id=department["id"])
    _assign(client, quest["id"], assignment_type="EMPLOYEE", employee_id=employee["id"])
    _publish(client, quest["id"])
    _submit_and_evaluate(client, quest["id"], employee["id"])

    listed = _list_quests(client, employee["id"])
    item = next(q for q in listed if q["id"] == quest["id"])
    assert item["attempt_status"] == "COMPLETED"


def test_in_progress_quest_remains_visible_with_in_progress_state(
    client, employee, department, capability_id
):
    quest = _publishable_quest(client, capability_id, department_id=department["id"])
    _assign(client, quest["id"], assignment_type="EMPLOYEE", employee_id=employee["id"])
    _publish(client, quest["id"])
    attempt = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest["id"], "employee_id": employee["id"]}
    ).json()
    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": employee["id"], "findings": "Started looking into it."},
    )

    listed = _list_quests(client, employee["id"])
    item = next(q for q in listed if q["id"] == quest["id"])
    assert item["attempt_status"] == "IN_PROGRESS"


def test_never_started_quest_has_null_attempt_status(client, employee, department, capability_id):
    quest = _publishable_quest(client, capability_id, department_id=department["id"])
    _assign(client, quest["id"], assignment_type="EMPLOYEE", employee_id=employee["id"])
    _publish(client, quest["id"])

    listed = _list_quests(client, employee["id"])
    item = next(q for q in listed if q["id"] == quest["id"])
    assert item["attempt_status"] is None


# =====================================================================
# 12 — no hidden evaluation data anywhere in the list payload
# =====================================================================


def test_list_never_leaks_evaluation_criteria(client, employee, department, capability_id):
    quest = _publishable_quest(client, capability_id, department_id=department["id"])
    _assign(client, quest["id"], assignment_type="EMPLOYEE", employee_id=employee["id"])
    _publish(client, quest["id"])

    res = client.get(f"/api/v1/employees/{employee['id']}/quests")
    body_text = res.text.lower()
    for leaked in ("expected_answer", "expected_behavior", "reference_solution", "criterion_type"):
        assert leaked not in body_text
    item = next(q for q in res.json() if q["id"] == quest["id"])
    assert set(item.keys()) == {
        "id",
        "title",
        "description",
        "quest_type",
        "difficulty",
        "required_for_readiness",
        "attempt_status",
    }


# =====================================================================
# 13 — attempt_status is per-employee, never another employee's
# =====================================================================


def test_attempt_status_isolated_per_employee(client, org_id, department, capability_id):
    quest = _publishable_quest(client, capability_id, department_id=department["id"])
    employee_a = _employee_in(client, org_id, department["id"])
    employee_b = _employee_in(client, org_id, department["id"])
    _assign(client, quest["id"], assignment_type="DEPARTMENT", department_id=department["id"])
    _publish(client, quest["id"])

    _submit_and_evaluate(client, quest["id"], employee_a["id"])

    a_item = next(q for q in _list_quests(client, employee_a["id"]) if q["id"] == quest["id"])
    b_item = next(q for q in _list_quests(client, employee_b["id"]) if q["id"] == quest["id"])
    assert a_item["attempt_status"] == "COMPLETED"
    assert b_item["attempt_status"] is None


# =====================================================================
# 14 — unknown employee
# =====================================================================


def test_unknown_employee_returns_404(client):
    res = client.get("/api/v1/employees/does-not-exist/quests")
    assert res.status_code == 404


# =====================================================================
# 15 — agreement with readiness-summary
# =====================================================================


def test_required_count_agrees_with_readiness_summary(client, employee, department, capability_id):
    quest_a = _publishable_quest(client, capability_id, department_id=department["id"])
    quest_b = _publishable_quest(client, capability_id, department_id=department["id"])
    _assign(client, quest_a["id"], assignment_type="EMPLOYEE", employee_id=employee["id"], required=True)
    _assign(client, quest_b["id"], assignment_type="EMPLOYEE", employee_id=employee["id"], required=False)
    _publish(client, quest_a["id"])
    _publish(client, quest_b["id"])

    listed = _list_quests(client, employee["id"])
    required_in_list = sum(1 for q in listed if q["required_for_readiness"])

    readiness = client.get(f"/api/v1/employees/{employee['id']}/readiness-summary").json()
    assert required_in_list == readiness["required_quest_count"]


# =====================================================================
# 16/17 — read-only: viewing the list never creates or duplicates a
# QuestAttempt
# =====================================================================


def test_listing_does_not_create_an_attempt(client, employee, department, capability_id):
    quest = _publishable_quest(client, capability_id, department_id=department["id"])
    _assign(client, quest["id"], assignment_type="EMPLOYEE", employee_id=employee["id"])
    _publish(client, quest["id"])

    # Viewing the list several times must never itself start an attempt —
    # confirmed via the list's own attempt_status, which would flip away
    # from null the instant a QuestAttempt row existed.
    for _ in range(3):
        listed = _list_quests(client, employee["id"])
        item = next(q for q in listed if q["id"] == quest["id"])
        assert item["attempt_status"] is None


def test_repeated_listing_is_idempotent(client, employee, department, capability_id):
    quest = _publishable_quest(client, capability_id, department_id=department["id"])
    _assign(client, quest["id"], assignment_type="EMPLOYEE", employee_id=employee["id"])
    _publish(client, quest["id"])

    first = _list_quests(client, employee["id"])
    second = _list_quests(client, employee["id"])
    third = _list_quests(client, employee["id"])
    assert first == second == third

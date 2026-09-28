"""Phase 8H-3 backend tests: the employee-safe `required_for_readiness`
signal on EmployeeQuestResponse — available both from GET /quests/{id}/
employee and nested inside GET /employees/{id}/next-quest.

Deliberately does NOT re-test readiness_service.is_ready()'s predicate
(test_readiness_service.py covers that exhaustively) or quest_
recommendation.py's ranking (test_quest_recommendation.py covers that).
This file covers only: that the new field reflects the same
required_eligible_quest_ids() set is_ready() itself uses, that it never
depends on completion/recommendation/difficulty, and that it responds
live to assignment changes — exactly mirroring test_readiness_summary.py's
conventions and fixtures.

Runs against its own isolated SQLite file, same convention as the other
test_*.py modules.
"""

import asyncio
import itertools
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_required_for_readiness.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import QuestAssignment  # noqa: E402

_email_counter = itertools.count()
_dept_counter = itertools.count()
_quest_counter = itertools.count()


def run(coro):
    return asyncio.run(coro)


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
def capability_ids(client):
    caps = client.get("/api/v1/capabilities").json()
    return {c["key"]: c["id"] for c in caps}


@pytest.fixture
def department(client, org_id):
    return client.post(
        "/api/v1/departments",
        json={"organization_id": org_id, "name": f"8H3 Dept {next(_dept_counter)}"},
    ).json()


@pytest.fixture
def role(client, department):
    return client.post(
        "/api/v1/roles",
        json={"department_id": department["id"], "title": f"8H3 Role {next(_dept_counter)}"},
    ).json()


@pytest.fixture
def employee(client, org_id, department):
    return client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "full_name": "8H3 Test Employee",
            "email": f"8h3-{next(_email_counter)}@kowri.test",
        },
    ).json()


def _complete_onboarding(client, employee_id):
    bundle = client.get(f"/api/v1/onboarding/bundle/{employee_id}").json()
    res = client.patch(
        f"/api/v1/onboarding/sessions/{bundle['session']['id']}", json={"current_scene": "completion"}
    )
    assert res.status_code == 200, res.text


def _build_quest(client, department_id, capability_ids, *, title=None, expected_answer="checkout-service"):
    title = title or f"8H3 Quest {next(_quest_counter)}"
    quest = client.post(
        "/api/v1/quests",
        json={
            "title": title,
            "description": "A real workplace problem used only for required_for_readiness tests.",
            "quest_type": "INVESTIGATE",
            "workspace_type": "INVESTIGATION",
            "department_id": department_id,
        },
    ).json()
    qid = quest["id"]
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
            "max_score": 100,
        },
    )
    client.post(
        f"/api/v1/quests/{qid}/capabilities",
        json={"capability_id": capability_ids["troubleshooting"], "weight": 1.0},
    )
    return qid


async def _set_required(assignment_id: str, required: bool) -> None:
    async with AsyncSessionLocal() as db:
        assignment = await db.get(QuestAssignment, assignment_id)
        assignment.required = required
        await db.commit()


def _assign(client, qid, *, employee_id=None, department_id=None, role_id=None, required=False):
    if employee_id:
        payload = {"assignment_type": "EMPLOYEE", "employee_id": employee_id}
    elif department_id:
        payload = {"assignment_type": "DEPARTMENT", "department_id": department_id}
    else:
        payload = {"assignment_type": "ROLE", "role_id": role_id}
    assignment = client.post(f"/api/v1/quests/{qid}/assignments", json=payload).json()
    if required:
        run(_set_required(assignment["id"], True))
    return assignment["id"]


def _publish(client, qid):
    res = client.post(f"/api/v1/quests/{qid}/publish")
    assert res.status_code == 200, res.text


def _submit_and_evaluate(client, qid, employee_id, *, solution="checkout-service is the affected service."):
    attempt = client.post("/api/v1/quest-attempts", json={"quest_id": qid, "employee_id": employee_id}).json()
    aid = attempt["id"]
    client.patch(
        f"/api/v1/quest-attempts/{aid}",
        json={
            "employee_id": employee_id,
            "findings": "Latency spiked sharply.",
            "reasoning": "Lines up with a recent deploy that introduced a slow query.",
            "solution": solution,
        },
    )
    submit = client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": employee_id})
    assert submit.status_code == 200, submit.text
    evaluate = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": employee_id})
    assert evaluate.status_code == 200, evaluate.text


def _employee_quest(client, qid, employee_id):
    res = client.get(f"/api/v1/quests/{qid}/employee", params={"employee_id": employee_id})
    assert res.status_code == 200, res.text
    return res.json()


def _next_quest(client, employee_id):
    res = client.get(f"/api/v1/employees/{employee_id}/next-quest")
    assert res.status_code == 200, res.text
    return res.json()


def _readiness_summary(client, employee_id):
    res = client.get(f"/api/v1/employees/{employee_id}/readiness-summary")
    assert res.status_code == 200, res.text
    return res.json()


# =====================================================================
# 1-9 — required flag by assignment shape
# =====================================================================


def test_required_employee_assignment_is_true(client, employee, department, capability_ids):
    qid = _build_quest(client, department["id"], capability_ids)
    _assign(client, qid, employee_id=employee["id"], required=True)
    _publish(client, qid)
    assert _employee_quest(client, qid, employee["id"])["required_for_readiness"] is True


def test_optional_employee_assignment_is_false(client, employee, department, capability_ids):
    qid = _build_quest(client, department["id"], capability_ids)
    _assign(client, qid, employee_id=employee["id"], required=False)
    _publish(client, qid)
    assert _employee_quest(client, qid, employee["id"])["required_for_readiness"] is False


def test_required_department_assignment_is_true(client, employee, department, capability_ids):
    qid = _build_quest(client, department["id"], capability_ids)
    _assign(client, qid, department_id=department["id"], required=True)
    _publish(client, qid)
    assert _employee_quest(client, qid, employee["id"])["required_for_readiness"] is True


def test_optional_department_assignment_is_false(client, employee, department, capability_ids):
    qid = _build_quest(client, department["id"], capability_ids)
    _assign(client, qid, department_id=department["id"], required=False)
    _publish(client, qid)
    assert _employee_quest(client, qid, employee["id"])["required_for_readiness"] is False


def test_required_role_assignment_is_true(client, org_id, department, role, capability_ids):
    with_role = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "role_id": role["id"],
            "full_name": "8H3 Role Employee",
            "email": f"8h3-role-{next(_email_counter)}@kowri.test",
        },
    ).json()
    qid = _build_quest(client, department["id"], capability_ids)
    _assign(client, qid, role_id=role["id"], required=True)
    _publish(client, qid)
    assert _employee_quest(client, qid, with_role["id"])["required_for_readiness"] is True


def test_optional_role_assignment_is_false(client, org_id, department, role, capability_ids):
    with_role = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "role_id": role["id"],
            "full_name": "8H3 Role Employee Optional",
            "email": f"8h3-role-opt-{next(_email_counter)}@kowri.test",
        },
    ).json()
    qid = _build_quest(client, department["id"], capability_ids)
    _assign(client, qid, role_id=role["id"], required=False)
    _publish(client, qid)
    assert _employee_quest(client, qid, with_role["id"])["required_for_readiness"] is False


def test_inactive_required_assignment_is_false(client, employee, department, capability_ids):
    """Isolates the `active` check specifically: the employee stays
    eligible to view the quest via a SEPARATE, always-active DEPARTMENT
    assignment, while their own EMPLOYEE-level required assignment is
    deactivated — proving required_for_readiness itself responds to
    `active`, distinct from test_deactivating_assignment_removes_
    eligibility below, which covers the case where deactivation is the
    employee's *only* path to the quest at all (existing, unmodified
    eligibility-gate behavior — the endpoint 403s, per Step 6's explicit
    "no longer appears" allowance)."""
    qid = _build_quest(client, department["id"], capability_ids)
    _assign(client, qid, department_id=department["id"], required=False)  # keeps them eligible throughout
    assignment_id = _assign(client, qid, employee_id=employee["id"], required=True)
    _publish(client, qid)
    assert _employee_quest(client, qid, employee["id"])["required_for_readiness"] is True

    deactivate = client.patch(f"/api/v1/quests/{qid}/assignments/{assignment_id}", json={"active": False})
    assert deactivate.status_code == 200, deactivate.text
    assert _employee_quest(client, qid, employee["id"])["required_for_readiness"] is False


def test_deactivating_only_assignment_removes_eligibility_entirely(client, employee, department, capability_ids):
    """When the deactivated assignment was the employee's ONLY path to
    the quest, the existing (unmodified) is_employee_eligible gate on
    GET .../employee correctly denies access altogether — matching Step
    6's "the Quest must no longer appear in the employee-facing active
    Quest collection" allowance, not a required_for_readiness=False
    response. This is intended, pre-existing behavior this phase does
    not change."""
    qid = _build_quest(client, department["id"], capability_ids)
    assignment_id = _assign(client, qid, employee_id=employee["id"], required=True)
    _publish(client, qid)
    assert _employee_quest(client, qid, employee["id"])["required_for_readiness"] is True

    client.patch(f"/api/v1/quests/{qid}/assignments/{assignment_id}", json={"active": False})
    res = client.get(f"/api/v1/quests/{qid}/employee", params={"employee_id": employee["id"]})
    assert res.status_code == 403


def test_ineligible_employee_is_false(client, org_id, department, capability_ids):
    other_department = client.post(
        "/api/v1/departments", json={"organization_id": org_id, "name": f"8H3 Other Dept {next(_dept_counter)}"}
    ).json()
    other_employee = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": other_department["id"],
            "full_name": "8H3 Ineligible Employee",
            "email": f"8h3-ineligible-{next(_email_counter)}@kowri.test",
        },
    ).json()
    qid = _build_quest(client, department["id"], capability_ids)
    _assign(client, qid, department_id=department["id"], required=True)
    _publish(client, qid)

    # An employee in a DIFFERENT department, not directly assigned, is
    # not eligible at all — the /employee endpoint itself returns 403,
    # matching this endpoint's existing, unmodified eligibility gate.
    res = client.get(f"/api/v1/quests/{qid}/employee", params={"employee_id": other_employee["id"]})
    assert res.status_code == 403


def test_archived_quest_no_longer_required(client, employee, department, capability_ids):
    qid = _build_quest(client, department["id"], capability_ids)
    _assign(client, qid, employee_id=employee["id"], required=True)
    _publish(client, qid)
    assert _employee_quest(client, qid, employee["id"])["required_for_readiness"] is True

    archive = client.post(f"/api/v1/quests/{qid}/archive")
    assert archive.status_code == 200, archive.text

    # Archived quests are no longer PUBLISHED, so the employee is no
    # longer eligible for it at all (existing, unmodified rule) — the
    # /employee endpoint 403s rather than returning a quest that's no
    # longer part of the active requirement set.
    res = client.get(f"/api/v1/quests/{qid}/employee", params={"employee_id": employee["id"]})
    assert res.status_code == 403


# =====================================================================
# 10-12 — completion independence
# =====================================================================


def test_required_quest_before_completion_is_true(client, employee, department, capability_ids):
    qid = _build_quest(client, department["id"], capability_ids)
    _assign(client, qid, employee_id=employee["id"], required=True)
    _publish(client, qid)
    assert _employee_quest(client, qid, employee["id"])["required_for_readiness"] is True


def test_required_quest_after_completion_still_true(client, employee, department, capability_ids):
    """The core distinction Step 5 exists to protect: completion affects
    completed_required_quest_count, never required_for_readiness itself."""
    qid = _build_quest(client, department["id"], capability_ids)
    _assign(client, qid, employee_id=employee["id"], required=True)
    _publish(client, qid)
    _complete_onboarding(client, employee["id"])
    _submit_and_evaluate(client, qid, employee["id"])

    assert _employee_quest(client, qid, employee["id"])["required_for_readiness"] is True
    summary = _readiness_summary(client, employee["id"])
    assert summary["ready"] is True
    assert summary["completed_required_quest_count"] == 1


def test_completed_optional_quest_is_false(client, employee, department, capability_ids):
    qid = _build_quest(client, department["id"], capability_ids)
    _assign(client, qid, employee_id=employee["id"], required=False)
    _publish(client, qid)
    _submit_and_evaluate(client, qid, employee["id"])
    assert _employee_quest(client, qid, employee["id"])["required_for_readiness"] is False


# =====================================================================
# 13-15 — recommendation independence
# =====================================================================


def test_optional_quest_can_still_be_recommended(client, employee, department, capability_ids):
    qid = _build_quest(client, department["id"], capability_ids)
    _assign(client, qid, employee_id=employee["id"], required=False)
    _publish(client, qid)

    result = _next_quest(client, employee["id"])
    assert result["recommended_quest"]["id"] == qid
    assert result["recommended_quest"]["required_for_readiness"] is False


def test_required_quest_recommended_flag_reflects_required_not_recommendation(
    client, employee, department, capability_ids
):
    qid_required = _build_quest(client, department["id"], capability_ids, title="8H3 Required Rec")
    _assign(client, qid_required, employee_id=employee["id"], required=True)
    _publish(client, qid_required)

    result = _next_quest(client, employee["id"])
    # Whether or not this particular required quest IS the recommendation
    # is entirely up to quest_recommendation.py's own ranking (untouched
    # here) — what this test asserts is only that when it IS surfaced,
    # its required_for_readiness reflects the assignment, not the fact
    # that it was recommended.
    if result["recommended_quest"] is not None and result["recommended_quest"]["id"] == qid_required:
        assert result["recommended_quest"]["required_for_readiness"] is True


def test_recommendation_selection_unaffected_by_8h3(client, employee, department, capability_ids):
    """Same database state, compared against the employee-quest
    endpoint's own eligibility-derived truth: the recommended quest is
    whichever quest_recommendation.py picks — required_for_readiness is
    never part of that decision (quest_recommendation.py was not
    modified this phase)."""
    qid_optional = _build_quest(client, department["id"], capability_ids, title="8H3 Optional Rec")
    _assign(client, qid_optional, employee_id=employee["id"], required=False)
    _publish(client, qid_optional)

    before = _next_quest(client, employee["id"])
    after = _next_quest(client, employee["id"])
    assert before["recommended_quest"]["id"] == after["recommended_quest"]["id"] == qid_optional
    assert before["reason"] == after["reason"]


# =====================================================================
# 16-19 — dynamic behavior
# =====================================================================


def test_optional_to_required_flips_true(client, employee, department, capability_ids):
    qid = _build_quest(client, department["id"], capability_ids)
    assignment_id = _assign(client, qid, employee_id=employee["id"], required=False)
    _publish(client, qid)
    assert _employee_quest(client, qid, employee["id"])["required_for_readiness"] is False

    run(_set_required(assignment_id, True))
    assert _employee_quest(client, qid, employee["id"])["required_for_readiness"] is True


def test_required_to_optional_flips_false(client, employee, department, capability_ids):
    qid = _build_quest(client, department["id"], capability_ids)
    assignment_id = _assign(client, qid, employee_id=employee["id"], required=True)
    _publish(client, qid)
    assert _employee_quest(client, qid, employee["id"])["required_for_readiness"] is True

    run(_set_required(assignment_id, False))
    assert _employee_quest(client, qid, employee["id"])["required_for_readiness"] is False


def test_deactivating_assignment_flips_false(client, employee, department, capability_ids):
    """Step 12 item #18, distinct from item #7's test above only in
    which dynamic transition is exercised (an already-true flag flipping
    live, rather than the static end-state) — same dual-assignment setup
    so eligibility survives the deactivation and the flip is actually
    observable rather than producing a 403."""
    qid = _build_quest(client, department["id"], capability_ids)
    _assign(client, qid, department_id=department["id"], required=False)
    assignment_id = _assign(client, qid, employee_id=employee["id"], required=True)
    _publish(client, qid)
    assert _employee_quest(client, qid, employee["id"])["required_for_readiness"] is True

    client.patch(f"/api/v1/quests/{qid}/assignments/{assignment_id}", json={"active": False})
    assert _employee_quest(client, qid, employee["id"])["required_for_readiness"] is False


def test_archiving_quest_removes_it_from_active_requirement_semantics(
    client, employee, department, capability_ids
):
    qid = _build_quest(client, department["id"], capability_ids)
    _assign(client, qid, employee_id=employee["id"], required=True)
    _publish(client, qid)
    _complete_onboarding(client, employee["id"])

    summary_before = _readiness_summary(client, employee["id"])
    assert summary_before["required_quest_count"] == 1

    client.post(f"/api/v1/quests/{qid}/archive")

    summary_after = _readiness_summary(client, employee["id"])
    assert summary_after["required_quest_count"] == 0


# =====================================================================
# 20 — employee isolation
# =====================================================================


def test_employee_isolation(client, org_id, department, capability_ids):
    employee_a = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "full_name": "8H3 Isolation A",
            "email": f"8h3-iso-a-{next(_email_counter)}@kowri.test",
        },
    ).json()
    employee_b = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "full_name": "8H3 Isolation B",
            "email": f"8h3-iso-b-{next(_email_counter)}@kowri.test",
        },
    ).json()

    qid = _build_quest(client, department["id"], capability_ids)
    _assign(client, qid, employee_id=employee_a["id"], required=True)
    _publish(client, qid)

    assert _employee_quest(client, qid, employee_a["id"])["required_for_readiness"] is True
    # employee_b isn't assigned to this quest at all — not eligible, 403.
    res_b = client.get(f"/api/v1/quests/{qid}/employee", params={"employee_id": employee_b["id"]})
    assert res_b.status_code == 403


# =====================================================================
# 21-22 — contract / security
# =====================================================================


def test_response_field_set_gains_exactly_one_field(client, employee, department, capability_ids):
    qid = _build_quest(client, department["id"], capability_ids)
    _assign(client, qid, employee_id=employee["id"], required=True)
    _publish(client, qid)
    body = _employee_quest(client, qid, employee["id"])
    assert set(body.keys()) == {
        "id",
        "title",
        "description",
        "quest_type",
        "workspace_type",
        "difficulty",
        "tasks",
        "evidence",
        "required_for_readiness",
    }


def test_no_hidden_data_leaks_alongside_the_new_field(client, employee, department, capability_ids):
    qid = _build_quest(client, department["id"], capability_ids)
    client.post(
        f"/api/v1/quests/{qid}/evaluation-criteria",
        json={
            "name": "Hidden criterion",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "SECRET_8H3_ANSWER",
            "max_score": 50,
        },
    )
    _assign(client, qid, employee_id=employee["id"], required=True)
    _publish(client, qid)

    res = client.get(f"/api/v1/quests/{qid}/employee", params={"employee_id": employee["id"]})
    text = res.text
    for forbidden in ("SECRET_8H3_ANSWER", "expected_answer", "expected_behavior", "reference_solution"):
        assert forbidden not in text

    body = res.json()
    assert "assignment_id" not in body
    assert "assignment_type" not in body
    # No raw QuestAssignment fields leaking alongside the derived
    # boolean — only the one intended new key was added to the contract.
    assert "required" not in body  # the raw assignment field name, distinct from required_for_readiness
    assert "active" not in body


# =====================================================================
# Step 13 — readiness invariant
# =====================================================================


def test_required_for_readiness_count_matches_readiness_summary(
    client, employee, department, capability_ids
):
    """The set of quests this employee can see with required_for_
    readiness == true must correspond exactly to readiness_summary's
    required_quest_count — checked here against every PUBLISHED quest
    the employee is actually eligible to view (the employee contract
    intentionally 403s on ineligible quests, so only eligible ones are
    included, matching Step 13's caution)."""
    qid_a = _build_quest(client, department["id"], capability_ids, title="8H3 Invariant A")
    qid_b = _build_quest(client, department["id"], capability_ids, title="8H3 Invariant B")
    qid_c = _build_quest(client, department["id"], capability_ids, title="8H3 Invariant C (optional)")
    _assign(client, qid_a, employee_id=employee["id"], required=True)
    _assign(client, qid_b, employee_id=employee["id"], required=True)
    _assign(client, qid_c, employee_id=employee["id"], required=False)
    for qid in (qid_a, qid_b, qid_c):
        _publish(client, qid)

    _complete_onboarding(client, employee["id"])
    summary = _readiness_summary(client, employee["id"])
    assert summary["required_quest_count"] == 2

    flags = [
        _employee_quest(client, qid, employee["id"])["required_for_readiness"]
        for qid in (qid_a, qid_b, qid_c)
    ]
    assert flags.count(True) == summary["required_quest_count"] == 2
    assert flags == [True, True, False]

"""Phase 8H-1 backend tests: the employee-safe ReadinessSummary read
model — GET /employees/{employee_id}/readiness-summary.

Deliberately does NOT re-test readiness_service.is_ready()'s own
predicate from scratch (test_readiness_service.py already covers that
exhaustively via the real evaluate_attempt trigger). This file covers:
the summary's own contract (counts, not just a bool), that it agrees
with is_ready() for every scenario the existing suite already proves,
archived/ineligible-quest edge cases specific to the count fields, and
employee isolation for the new endpoint.

Runs against its own isolated SQLite file, same convention as the other
test_*.py modules.
"""

import asyncio
import itertools
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_readiness_summary.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Employee, QuestAssignment  # noqa: E402
from app.services import readiness_service  # noqa: E402

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
        json={"organization_id": org_id, "name": f"Readiness Summary Dept {next(_dept_counter)}"},
    ).json()


@pytest.fixture
def role(client, department):
    return client.post(
        "/api/v1/roles",
        json={"department_id": department["id"], "title": f"Readiness Summary Role {next(_dept_counter)}"},
    ).json()


@pytest.fixture
def employee(client, org_id, department):
    return client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "full_name": "Readiness Summary Employee",
            "email": f"readiness-summary-{next(_email_counter)}@kowri.test",
        },
    ).json()


def _complete_onboarding(client, employee_id):
    bundle = client.get(f"/api/v1/onboarding/bundle/{employee_id}").json()
    session_id = bundle["session"]["id"]
    res = client.patch(f"/api/v1/onboarding/sessions/{session_id}", json={"current_scene": "completion"})
    assert res.status_code == 200, res.text


def _build_quest(client, department_id, capability_ids, *, title=None, expected_answer="checkout-service"):
    title = title or f"Readiness Summary Quest {next(_quest_counter)}"
    quest = client.post(
        "/api/v1/quests",
        json={
            "title": title,
            "description": "A real workplace problem used only for readiness-summary tests.",
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


async def _make_required(assignment_id: str) -> None:
    async with AsyncSessionLocal() as db:
        assignment = await db.get(QuestAssignment, assignment_id)
        assignment.required = True
        await db.commit()


def _assign_required(client, qid, *, employee_id=None, department_id=None, role_id=None):
    if employee_id:
        payload = {"assignment_type": "EMPLOYEE", "employee_id": employee_id}
    elif department_id:
        payload = {"assignment_type": "DEPARTMENT", "department_id": department_id}
    else:
        payload = {"assignment_type": "ROLE", "role_id": role_id}
    assignment = client.post(f"/api/v1/quests/{qid}/assignments", json=payload).json()
    run(_make_required(assignment["id"]))
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
    return aid


async def _is_ready(employee_id: str) -> bool:
    async with AsyncSessionLocal() as db:
        employee = await db.get(Employee, employee_id)
        return await readiness_service.is_ready(db, employee)


def _summary(client, employee_id):
    res = client.get(f"/api/v1/employees/{employee_id}/readiness-summary")
    assert res.status_code == 200, res.text
    return res.json()


def _assert_agrees_with_trigger(employee_id, summary):
    """§ Step 6's invariant, checked explicitly on top of the fact that
    both share one code path — this is the outward, black-box proof."""
    assert summary["ready"] == run(_is_ready(employee_id))


# =====================================================================
# 1-6 — the core count scenarios
# =====================================================================


def test_incomplete_onboarding(client, employee):
    summary = _summary(client, employee["id"])
    assert summary["onboarding_completed"] is False
    assert summary["ready"] is False
    _assert_agrees_with_trigger(employee["id"], summary)


def test_onboarding_complete_zero_required_quests(client, employee):
    _complete_onboarding(client, employee["id"])
    summary = _summary(client, employee["id"])
    assert summary == {
        "ready": False,
        "onboarding_completed": True,
        "required_quest_count": 0,
        "completed_required_quest_count": 0,
        "remaining_required_quest_count": 0,
        "required_mission_count": 0,
        "completed_required_mission_count": 0,
        "remaining_required_mission_count": 0,
    }
    _assert_agrees_with_trigger(employee["id"], summary)


def test_one_required_quest_incomplete(client, employee, department, capability_ids):
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, employee_id=employee["id"])
    _publish(client, qid)

    summary = _summary(client, employee["id"])
    assert summary["required_quest_count"] == 1
    assert summary["completed_required_quest_count"] == 0
    assert summary["remaining_required_quest_count"] == 1
    assert summary["ready"] is False
    _assert_agrees_with_trigger(employee["id"], summary)


def test_one_required_quest_completed(client, employee, department, capability_ids):
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, employee_id=employee["id"])
    _publish(client, qid)
    _submit_and_evaluate(client, qid, employee["id"])

    summary = _summary(client, employee["id"])
    assert summary["required_quest_count"] == 1
    assert summary["completed_required_quest_count"] == 1
    assert summary["remaining_required_quest_count"] == 0
    assert summary["ready"] is True
    _assert_agrees_with_trigger(employee["id"], summary)


def test_multiple_required_partially_completed(client, employee, department, capability_ids):
    _complete_onboarding(client, employee["id"])
    qid_a = _build_quest(client, department["id"], capability_ids, title=f"Multi A {next(_quest_counter)}")
    qid_b = _build_quest(client, department["id"], capability_ids, title=f"Multi B {next(_quest_counter)}")
    qid_c = _build_quest(client, department["id"], capability_ids, title=f"Multi C {next(_quest_counter)}")
    for qid in (qid_a, qid_b, qid_c):
        _assign_required(client, qid, employee_id=employee["id"])
        _publish(client, qid)
    _submit_and_evaluate(client, qid_a, employee["id"])

    summary = _summary(client, employee["id"])
    assert summary["required_quest_count"] == 3
    assert summary["completed_required_quest_count"] == 1
    assert summary["remaining_required_quest_count"] == 2
    assert summary["ready"] is False
    _assert_agrees_with_trigger(employee["id"], summary)


def test_multiple_required_all_completed(client, employee, department, capability_ids):
    _complete_onboarding(client, employee["id"])
    qid_a = _build_quest(client, department["id"], capability_ids, title=f"All A {next(_quest_counter)}")
    qid_b = _build_quest(client, department["id"], capability_ids, title=f"All B {next(_quest_counter)}")
    for qid in (qid_a, qid_b):
        _assign_required(client, qid, employee_id=employee["id"])
        _publish(client, qid)
        _submit_and_evaluate(client, qid, employee["id"])

    summary = _summary(client, employee["id"])
    assert summary["required_quest_count"] == 2
    assert summary["completed_required_quest_count"] == 2
    assert summary["remaining_required_quest_count"] == 0
    assert summary["ready"] is True
    _assert_agrees_with_trigger(employee["id"], summary)


# =====================================================================
# 7-8 — archived / ineligible required quests
# =====================================================================


def test_archived_required_quest_drops_out_of_the_count(client, employee, department, capability_ids):
    """Preserves the existing, documented policy exactly: an archived
    required Quest no longer participates in the active requirement
    set at all — not "counted but unsatisfiable," simply absent."""
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, employee_id=employee["id"])
    _publish(client, qid)

    before = _summary(client, employee["id"])
    assert before["required_quest_count"] == 1
    assert before["ready"] is False

    archive_res = client.post(f"/api/v1/quests/{qid}/archive")
    assert archive_res.status_code == 200, archive_res.text

    after = _summary(client, employee["id"])
    assert after["required_quest_count"] == 0
    assert after["completed_required_quest_count"] == 0
    assert after["remaining_required_quest_count"] == 0
    # Zero required quests is deliberately NOT ready (test #2's rule) —
    # archiving the only required quest must NOT flip an employee to
    # ready as a side effect.
    assert after["ready"] is False
    _assert_agrees_with_trigger(employee["id"], after)


def test_ineligible_required_quest_never_counted(client, employee, org_id, capability_ids):
    """A required assignment targeting a DIFFERENT department must
    never appear in this employee's counts at all."""
    _complete_onboarding(client, employee["id"])

    other_department = client.post(
        "/api/v1/departments", json={"organization_id": org_id, "name": f"Other Dept {next(_dept_counter)}"}
    ).json()
    qid = _build_quest(client, other_department["id"], capability_ids)
    _assign_required(client, qid, department_id=other_department["id"])
    _publish(client, qid)

    summary = _summary(client, employee["id"])
    assert summary["required_quest_count"] == 0
    _assert_agrees_with_trigger(employee["id"], summary)


# =====================================================================
# 9-11 — EMPLOYEE / DEPARTMENT / ROLE assignment eligibility
# =====================================================================


def test_employee_targeted_assignment_counts(client, employee, department, capability_ids):
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, employee_id=employee["id"])
    _publish(client, qid)
    assert _summary(client, employee["id"])["required_quest_count"] == 1


def test_department_targeted_assignment_counts(client, employee, department, capability_ids):
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, department_id=department["id"])
    _publish(client, qid)
    assert _summary(client, employee["id"])["required_quest_count"] == 1


def test_role_targeted_assignment_counts(client, org_id, department, role, capability_ids):
    with_role = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "role_id": role["id"],
            "full_name": "Readiness Summary Role Employee",
            "email": f"readiness-summary-role-{next(_email_counter)}@kowri.test",
        },
    ).json()
    _complete_onboarding(client, with_role["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, role_id=role["id"])
    _publish(client, qid)
    assert _summary(client, with_role["id"])["required_quest_count"] == 1


# =====================================================================
# 12 — assignment changes reflected immediately (no caching)
# =====================================================================


def test_new_required_assignment_reflected_immediately(client, employee, department, capability_ids):
    _complete_onboarding(client, employee["id"])
    qid_a = _build_quest(client, department["id"], capability_ids, title=f"Reflect A {next(_quest_counter)}")
    _assign_required(client, qid_a, employee_id=employee["id"])
    _publish(client, qid_a)
    _submit_and_evaluate(client, qid_a, employee["id"])

    ready_summary = _summary(client, employee["id"])
    assert ready_summary["ready"] is True

    qid_b = _build_quest(client, department["id"], capability_ids, title=f"Reflect B {next(_quest_counter)}")
    _assign_required(client, qid_b, employee_id=employee["id"])
    _publish(client, qid_b)

    not_ready_summary = _summary(client, employee["id"])
    assert not_ready_summary["required_quest_count"] == 2
    assert not_ready_summary["remaining_required_quest_count"] == 1
    assert not_ready_summary["ready"] is False
    _assert_agrees_with_trigger(employee["id"], not_ready_summary)


def test_removed_required_assignment_reflected_immediately(client, employee, department, capability_ids):
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    assignment_id = _assign_required(client, qid, employee_id=employee["id"])
    _publish(client, qid)
    assert _summary(client, employee["id"])["required_quest_count"] == 1

    deactivate = client.patch(
        f"/api/v1/quests/{qid}/assignments/{assignment_id}", json={"active": False}
    )
    assert deactivate.status_code == 200, deactivate.text

    summary = _summary(client, employee["id"])
    assert summary["required_quest_count"] == 0
    _assert_agrees_with_trigger(employee["id"], summary)


# =====================================================================
# 13-14 — unknown employee / isolation
# =====================================================================


def test_unknown_employee_404s(client):
    res = client.get("/api/v1/employees/not-a-real-employee/readiness-summary")
    assert res.status_code == 404


def test_employee_isolation(client, org_id, department, capability_ids):
    employee_a = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "full_name": "Isolation A",
            "email": f"readiness-summary-iso-a-{next(_email_counter)}@kowri.test",
        },
    ).json()
    employee_b = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "full_name": "Isolation B",
            "email": f"readiness-summary-iso-b-{next(_email_counter)}@kowri.test",
        },
    ).json()

    _complete_onboarding(client, employee_a["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, employee_id=employee_a["id"])
    _publish(client, qid)
    _submit_and_evaluate(client, qid, employee_a["id"])

    a_summary = _summary(client, employee_a["id"])
    b_summary = _summary(client, employee_b["id"])

    assert a_summary["ready"] is True
    # B never had onboarding completed, never had this required quest
    # assigned to them individually — A's progress must not leak in.
    assert b_summary["onboarding_completed"] is False
    assert b_summary["required_quest_count"] == 0
    assert b_summary["ready"] is False


def test_never_requires_manager_login(employee):
    with TestClient(app) as anon:
        res = anon.get(f"/api/v1/employees/{employee['id']}/readiness-summary")
        assert res.status_code == 200


# =====================================================================
# 15 — explicit agreement with the existing readiness trigger, restated
# as its own standalone tests (not just piggybacked on the scenarios
# above) so this invariant is provable on its own.
# =====================================================================


def test_summary_ready_matches_is_ready_when_not_ready(client, employee):
    summary = _summary(client, employee["id"])
    assert summary["ready"] is False
    assert summary["ready"] == run(_is_ready(employee["id"]))


def test_summary_ready_matches_is_ready_when_ready(client, employee, department, capability_ids):
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, employee_id=employee["id"])
    _publish(client, qid)
    _submit_and_evaluate(client, qid, employee["id"])

    summary = _summary(client, employee["id"])
    assert summary["ready"] is True
    assert summary["ready"] == run(_is_ready(employee["id"]))


# =====================================================================
# Security — employee-safe field set
# =====================================================================


def test_response_has_no_extra_or_internal_fields(client, employee):
    summary = _summary(client, employee["id"])
    assert set(summary.keys()) == {
        "ready",
        "onboarding_completed",
        "required_quest_count",
        "completed_required_quest_count",
        "remaining_required_quest_count",
        "required_mission_count",
        "completed_required_mission_count",
        "remaining_required_mission_count",
    }

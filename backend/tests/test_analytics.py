"""Phase 6E backend tests: Manager Analytics — a read-only aggregation
layer over Quest/QuestAttempt/QuestAssignment/CapabilityEvidence/
CapabilityProfile/Recommendation.

Runs against an isolated SQLite file, deleted and recreated each run —
same convention as the other test_quest_*.py modules.
"""

import asyncio
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_analytics.db"
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
def org_id(demo_bundle):
    return demo_bundle["employee"]["organization_id"]


@pytest.fixture(scope="module")
def department_id(client, org_id):
    """A dedicated, freshly-created department — see
    test_quest_recommendation.py for why: every test file shares one
    physical database when the full suite runs in one pytest process."""
    res = client.post(
        "/api/v1/departments", json={"organization_id": org_id, "name": "6E Analytics Tests Dept"}
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


@pytest.fixture(scope="module")
def capability_ids(client):
    caps = client.get("/api/v1/capabilities").json()
    return {c["key"]: c["id"] for c in caps}


_employee_counter = 0


def _new_employee(client, org_id, department_id, *, name_prefix="6E Employee"):
    global _employee_counter
    _employee_counter += 1
    res = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department_id,
            "full_name": f"{name_prefix} {_employee_counter}",
            "email": f"6e-employee-{_employee_counter}@buddy.dev",
            "start_date": "2026-01-01",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _new_quest(client, department_id=None, *, title, quest_type="OTHER", workspace_type="GENERAL"):
    payload = {"title": title, "quest_type": quest_type, "workspace_type": workspace_type, "description": "d"}
    if department_id:
        payload["department_id"] = department_id
    return client.post("/api/v1/quests", json=payload).json()


def _add_task(client, quest_id, *, task_type="OTHER", required=False):
    res = client.post(
        f"/api/v1/quests/{quest_id}/tasks", json={"title": "t", "task_type": task_type, "required": required}
    )
    assert res.status_code == 201, res.text


def _add_criterion(client, quest_id, **kwargs):
    payload = {"name": kwargs.pop("name", "c")}
    payload.update(kwargs)
    res = client.post(f"/api/v1/quests/{quest_id}/evaluation-criteria", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def _map_capability(client, quest_id, capability_id):
    res = client.post(f"/api/v1/quests/{quest_id}/capabilities", json={"capability_id": capability_id})
    assert res.status_code == 201, res.text


def _assign_employee(client, quest_id, employee_id):
    res = client.post(
        f"/api/v1/quests/{quest_id}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee_id},
    )
    assert res.status_code == 201, res.text


def _assign_department(client, quest_id, department_id):
    res = client.post(
        f"/api/v1/quests/{quest_id}/assignments",
        json={"assignment_type": "DEPARTMENT", "department_id": department_id},
    )
    assert res.status_code == 201, res.text


def _publish(client, quest_id):
    res = client.post(f"/api/v1/quests/{quest_id}/publish")
    assert res.status_code == 200, res.text
    return res.json()


def _make_simple_quest(client, capability_id, employee_id, *, title, department_id=None):
    quest = _new_quest(client, department_id, title=title)
    _add_task(client, quest["id"])
    _add_criterion(client, quest["id"], criterion_type="QUALITATIVE", description="ok")
    _map_capability(client, quest["id"], capability_id)
    _assign_employee(client, quest["id"], employee_id)
    return _publish(client, quest["id"])


def _complete_quest(client, quest_id, employee_id, solution="Resolved it."):
    attempt = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest_id, "employee_id": employee_id}
    ).json()
    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}", json={"employee_id": employee_id, "solution": solution}
    )
    submit = client.post(f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": employee_id})
    assert submit.status_code == 200, submit.text
    evaluate = client.post(
        f"/api/v1/quest-attempts/{attempt['id']}/evaluate", json={"employee_id": employee_id}
    )
    assert evaluate.status_code == 200, evaluate.text
    return attempt


def _start_quest_no_complete(client, quest_id, employee_id):
    """Reaches IN_PROGRESS only — autosave without submit."""
    attempt = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest_id, "employee_id": employee_id}
    ).json()
    res = client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": employee_id, "findings": "still looking into it"},
    )
    assert res.status_code == 200, res.text
    return attempt


def _next_quest(client, employee_id):
    res = client.get(f"/api/v1/employees/{employee_id}/next-quest")
    assert res.status_code == 200, res.text
    return res.json()


def _overview(client, department_id=None):
    params = {"department_id": department_id} if department_id else {}
    res = client.get("/api/v1/analytics/overview", params=params)
    assert res.status_code == 200, res.text
    return res.json()


def _quest_analytics(client, department_id=None):
    params = {"department_id": department_id} if department_id else {}
    res = client.get("/api/v1/analytics/quests", params=params)
    assert res.status_code == 200, res.text
    return res.json()


def _quest_detail(client, quest_id, department_id=None):
    params = {"department_id": department_id} if department_id else {}
    res = client.get(f"/api/v1/analytics/quests/{quest_id}", params=params)
    return res


def _capability_analytics(client, department_id=None):
    params = {"department_id": department_id} if department_id else {}
    res = client.get("/api/v1/analytics/capabilities", params=params)
    assert res.status_code == 200, res.text
    return res.json()


def _development_signals(client, department_id=None):
    params = {"department_id": department_id} if department_id else {}
    res = client.get("/api/v1/analytics/development-signals", params=params)
    assert res.status_code == 200, res.text
    return res.json()


def _employee_analytics(client, employee_id):
    return client.get(f"/api/v1/analytics/employees/{employee_id}")


def _quest_row_count():
    from app.db.session import AsyncSessionLocal
    from app.models import Quest, QuestAttempt, Recommendation
    from sqlalchemy import func, select

    async def _count():
        async with AsyncSessionLocal() as db:
            quest_count = (await db.execute(select(func.count()).select_from(Quest))).scalar_one()
            attempt_count = (await db.execute(select(func.count()).select_from(QuestAttempt))).scalar_one()
            rec_count = (await db.execute(select(func.count()).select_from(Recommendation))).scalar_one()
            return quest_count, attempt_count, rec_count

    return asyncio.run(_count())


# =====================================================================
# Overview (1-5)
# =====================================================================


def test_overview_correct_quest_counts(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    quest = _make_simple_quest(
        client, capability_ids["documentation"], employee_id, title="Overview quest counts", department_id=department_id
    )
    before = _overview(client, department_id)
    assert before["published_quests"] >= 1

    draft = _new_quest(client, department_id, title="Overview draft quest")
    after = _overview(client, department_id)
    assert after["draft_quests"] == before["draft_quests"] + 1
    assert after["published_quests"] == before["published_quests"]
    assert draft["status"] == "DRAFT"
    assert quest["status"] == "PUBLISHED"


def test_overview_correct_attempt_counts(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    quest = _make_simple_quest(
        client, capability_ids["documentation"], employee_id, title="Overview attempt counts", department_id=department_id
    )
    before = _overview(client, department_id)
    _start_quest_no_complete(client, quest["id"], employee_id)
    after = _overview(client, department_id)
    assert after["attempts_total"] == before["attempts_total"] + 1
    assert after["attempts_in_progress"] == before["attempts_in_progress"] + 1


def test_overview_correct_completion_counts(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    quest = _make_simple_quest(
        client, capability_ids["documentation"], employee_id, title="Overview completion counts", department_id=department_id
    )
    before = _overview(client, department_id)
    _complete_quest(client, quest["id"], employee_id)
    after = _overview(client, department_id)
    assert after["attempts_completed"] == before["attempts_completed"] + 1


def test_overview_correct_recommendation_counts(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Overview rec employee")
    quest_a = _make_simple_quest(
        client, capability_ids["documentation"], employee_id, title="Overview rec quest A", department_id=department_id
    )
    quest_b = _make_simple_quest(
        client, capability_ids["communication"], employee_id, title="Overview rec quest B", department_id=department_id
    )
    before = _overview(client, department_id)
    _next_quest(client, employee_id)
    after = _overview(client, department_id)
    assert after["recommendations_generated"] == before["recommendations_generated"] + 1
    assert quest_a["id"] != quest_b["id"]


def test_overview_recent_recommendations_content(client, org_id, capability_ids):
    dept = client.post("/api/v1/departments", json={"organization_id": org_id, "name": "6E Recent Recs Dept"}).json()["id"]
    employee_id = _new_employee(client, org_id, dept, name_prefix="Recent recs employee")
    quest = _make_simple_quest(client, capability_ids["documentation"], employee_id, title="Recent recs quest", department_id=dept)

    live = _next_quest(client, employee_id)
    overview = _overview(client, dept)
    assert len(overview["recent_recommendations"]) == 1
    item = overview["recent_recommendations"][0]
    assert item["employee_id"] == employee_id
    assert item["quest_id"] == quest["id"]
    assert item["quest_title"] == "Recent recs quest"
    assert item["reason"] == live["reason"]
    assert item["target_capabilities"] == live["target_capabilities"]


def test_overview_correct_capability_evidence_counts(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    quest = _make_simple_quest(
        client, capability_ids["independence"], employee_id, title="Overview evidence counts", department_id=department_id
    )
    before = _overview(client, department_id)
    _complete_quest(client, quest["id"], employee_id)
    after = _overview(client, department_id)
    assert after["capability_observations"] > before["capability_observations"]
    assert after["employees_with_capability_evidence"] >= before["employees_with_capability_evidence"] + 1


# =====================================================================
# Quest analytics (6-12)
# =====================================================================


def test_quest_analytics_aggregation(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    quest = _make_simple_quest(
        client, capability_ids["troubleshooting"], employee_id, title="Quest agg check", department_id=department_id
    )
    rows = _quest_analytics(client, department_id)["quests"]
    row = next(r for r in rows if r["quest_id"] == quest["id"])
    assert row["title"] == "Quest agg check"
    assert row["status"] == "PUBLISHED"
    assert row["capability_count"] == 1


def test_quest_analytics_assignment_counts(client, org_id, department_id, capability_ids):
    employee_a = _new_employee(client, org_id, department_id, name_prefix="Assign count A")
    employee_b = _new_employee(client, org_id, department_id, name_prefix="Assign count B")
    quest = _new_quest(client, department_id, title="Quest assignment reach")
    _add_task(client, quest["id"])
    _add_criterion(client, quest["id"], criterion_type="QUALITATIVE", description="ok")
    _map_capability(client, quest["id"], capability_ids["troubleshooting"])
    _assign_employee(client, quest["id"], employee_a)
    _assign_employee(client, quest["id"], employee_b)
    _publish(client, quest["id"])

    rows = _quest_analytics(client, department_id)["quests"]
    row = next(r for r in rows if r["quest_id"] == quest["id"])
    assert row["assigned_employees"] == 2


def test_quest_analytics_department_wide_assignment_reach(client, org_id, capability_ids):
    """DEPARTMENT-type assignments must resolve to actual employee
    membership, not just count as 1 assignment record — uses its own
    dedicated department to avoid leaking into other tests' employees."""
    dept_res = client.post("/api/v1/departments", json={"organization_id": org_id, "name": "6E Dept Reach Dept"})
    dept_id = dept_res.json()["id"]
    emp1 = _new_employee(client, org_id, dept_id, name_prefix="Dept reach 1")
    emp2 = _new_employee(client, org_id, dept_id, name_prefix="Dept reach 2")

    quest = _new_quest(client, dept_id, title="Dept-wide reach quest")
    _add_task(client, quest["id"])
    _add_criterion(client, quest["id"], criterion_type="QUALITATIVE", description="ok")
    _map_capability(client, quest["id"], capability_ids["troubleshooting"])
    _assign_department(client, quest["id"], dept_id)
    _publish(client, quest["id"])

    rows = _quest_analytics(client, dept_id)["quests"]
    row = next(r for r in rows if r["quest_id"] == quest["id"])
    assert row["assigned_employees"] == 2
    assert emp1 != emp2


def test_quest_analytics_attempt_and_completion_counts(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    quest = _make_simple_quest(
        client, capability_ids["troubleshooting"], employee_id, title="Quest attempt/completion counts", department_id=department_id
    )
    _complete_quest(client, quest["id"], employee_id)
    rows = _quest_analytics(client, department_id)["quests"]
    row = next(r for r in rows if r["quest_id"] == quest["id"])
    assert row["attempts_total"] == 1
    assert row["attempts_completed"] == 1
    assert row["completion_rate"] == 1.0


def test_quest_analytics_evidence_counts(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    quest = _make_simple_quest(
        client, capability_ids["troubleshooting"], employee_id, title="Quest evidence counts", department_id=department_id
    )
    _complete_quest(client, quest["id"], employee_id)
    rows = _quest_analytics(client, department_id)["quests"]
    row = next(r for r in rows if r["quest_id"] == quest["id"])
    assert row["evidence_count"] > 0


def test_quest_analytics_recommendation_counts(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Quest rec count employee")
    quest_a = _make_simple_quest(
        client, capability_ids["troubleshooting"], employee_id, title="Quest rec count A", department_id=department_id
    )
    _make_simple_quest(
        client, capability_ids["communication"], employee_id, title="Quest rec count B", department_id=department_id
    )
    _next_quest(client, employee_id)
    rows = _quest_analytics(client, department_id)["quests"]
    total_recs = sum(r["recommendation_count"] for r in rows if r["quest_id"] in (quest_a["id"],))
    assert total_recs >= 0  # sanity: field exists and is non-negative
    assert any(r["recommendation_count"] >= 1 for r in rows if r["title"] in ("Quest rec count A", "Quest rec count B"))


def test_quest_analytics_department_filtering_excludes_other_departments(client, org_id, capability_ids):
    dept_a = client.post("/api/v1/departments", json={"organization_id": org_id, "name": "6E Filter Dept A"}).json()["id"]
    dept_b = client.post("/api/v1/departments", json={"organization_id": org_id, "name": "6E Filter Dept B"}).json()["id"]
    emp_a = _new_employee(client, org_id, dept_a, name_prefix="Filter A")
    quest_a = _make_simple_quest(client, capability_ids["troubleshooting"], emp_a, title="Filter dept quest A", department_id=dept_a)

    rows_a = _quest_analytics(client, dept_a)["quests"]
    rows_b = _quest_analytics(client, dept_b)["quests"]
    assert any(r["quest_id"] == quest_a["id"] for r in rows_a)
    assert not any(r["quest_id"] == quest_a["id"] for r in rows_b)


# =====================================================================
# Capability analytics (13-16)
# =====================================================================


def test_capability_analytics_six_capabilities_represented(client, org_id, department_id):
    result = _capability_analytics(client, department_id)
    keys = {c["capability_key"] for c in result["capabilities"]}
    assert keys == {
        "technical_understanding",
        "troubleshooting",
        "problem_solving",
        "documentation",
        "communication",
        "independence",
    }


def test_capability_analytics_development_area_aggregation(client, org_id, capability_ids):
    dept = client.post("/api/v1/departments", json={"organization_id": org_id, "name": "6E Dev Area Dept"}).json()["id"]
    employee_id = _new_employee(client, org_id, dept, name_prefix="Dev area employee")
    quest = _make_simple_quest(client, capability_ids["problem_solving"], employee_id, title="Dev area quest", department_id=dept)
    _complete_quest(client, quest["id"], employee_id)

    result = _capability_analytics(client, dept)
    row = next(c for c in result["capabilities"] if c["capability_key"] == "problem_solving")
    assert row["development_area_employees"] == 1
    assert row["not_observed_employees"] == 0  # the only employee in this department now has a profile


def test_capability_analytics_level_aggregation_only_present_levels(client, org_id, capability_ids):
    dept = client.post("/api/v1/departments", json={"organization_id": org_id, "name": "6E Level Agg Dept"}).json()["id"]
    employee_id = _new_employee(client, org_id, dept, name_prefix="Level agg employee")
    quest = _make_simple_quest(client, capability_ids["independence"], employee_id, title="Level agg quest", department_id=dept)
    _complete_quest(client, quest["id"], employee_id)

    result = _capability_analytics(client, dept)
    row = next(c for c in result["capabilities"] if c["capability_key"] == "independence")
    levels_present = {b["level"] for b in row["level_breakdown"]}
    assert levels_present <= {"DEVELOPING", "CAPABLE", "STRONG"}
    assert "NOT_OBSERVED" not in levels_present  # never a stored level, per capability_profiles semantics


def test_capability_analytics_zero_evidence_capability(client, org_id):
    dept = client.post("/api/v1/departments", json={"organization_id": org_id, "name": "6E Zero Evidence Dept"}).json()["id"]
    _new_employee(client, org_id, dept, name_prefix="Zero evidence employee")

    result = _capability_analytics(client, dept)
    for row in result["capabilities"]:
        assert row["observed_employees"] == 0
        assert row["not_observed_employees"] == 1
        assert row["level_breakdown"] == []
        assert row["quests_producing_evidence"] == []


# =====================================================================
# Employee drill-down (17-20)
# =====================================================================


def test_employee_drilldown_context(client, org_id, department_id):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Drilldown context")
    res = _employee_analytics(client, employee_id)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["employee_id"] == employee_id
    assert body["department_id"] == department_id


def test_employee_drilldown_capability_data(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Drilldown capability")
    quest = _make_simple_quest(client, capability_ids["communication"], employee_id, title="Drilldown cap quest", department_id=department_id)
    _complete_quest(client, quest["id"], employee_id)

    body = _employee_analytics(client, employee_id).json()
    assert len(body["capabilities"]) == 6
    comm = next(c for c in body["capabilities"] if c["capability_key"] == "communication")
    assert comm["evidence_count"] > 0
    assert "communication" in body["development_areas"]


def test_employee_drilldown_quest_activity(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Drilldown quest activity")
    quest = _make_simple_quest(client, capability_ids["documentation"], employee_id, title="Drilldown activity quest", department_id=department_id)
    _complete_quest(client, quest["id"], employee_id)

    body = _employee_analytics(client, employee_id).json()
    activity = body["recent_quest_activity"]
    assert any(a["quest_id"] == quest["id"] and a["status"] == "COMPLETED" for a in activity)


def test_employee_drilldown_recommendation_activity(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Drilldown rec activity")
    _make_simple_quest(client, capability_ids["independence"], employee_id, title="Drilldown rec quest", department_id=department_id)
    _next_quest(client, employee_id)

    body = _employee_analytics(client, employee_id).json()
    assert body["latest_recommendation"] is not None
    assert body["latest_recommendation"]["target_capabilities"]


def test_employee_drilldown_unknown_employee_404(client):
    res = _employee_analytics(client, "does-not-exist")
    assert res.status_code == 404


def test_capability_employees_drilldown_reveals_correct_employees(client, org_id, capability_ids):
    dept = client.post("/api/v1/departments", json={"organization_id": org_id, "name": "6E Cap Drilldown Dept"}).json()["id"]
    dev_employee = _new_employee(client, org_id, dept, name_prefix="Cap drilldown developing")
    unobserved_employee = _new_employee(client, org_id, dept, name_prefix="Cap drilldown unobserved")

    quest = _make_simple_quest(client, capability_ids["troubleshooting"], dev_employee, title="Cap drilldown quest", department_id=dept)
    _complete_quest(client, quest["id"], dev_employee)

    res = client.get(
        f"/api/v1/analytics/capabilities/{capability_ids['troubleshooting']}/employees",
        params={"category": "DEVELOPMENT_AREA", "department_id": dept},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    employee_ids = {e["employee_id"] for e in body["employees"]}
    assert dev_employee in employee_ids
    assert unobserved_employee not in employee_ids
    assert body["employees"][0]["level"] == "DEVELOPING"
    assert body["employees"][0]["evidence_count"] > 0

    unobserved_res = client.get(
        f"/api/v1/analytics/capabilities/{capability_ids['troubleshooting']}/employees",
        params={"category": "UNOBSERVED", "department_id": dept},
    ).json()
    unobserved_ids = {e["employee_id"] for e in unobserved_res["employees"]}
    assert unobserved_employee in unobserved_ids
    assert dev_employee not in unobserved_ids


def test_capability_employees_drilldown_invalid_category(client, capability_ids):
    res = client.get(
        f"/api/v1/analytics/capabilities/{capability_ids['troubleshooting']}/employees",
        params={"category": "NOT_A_REAL_CATEGORY"},
    )
    assert res.status_code == 422


def test_capability_employees_drilldown_unknown_capability_404(client):
    res = client.get("/api/v1/analytics/capabilities/does-not-exist/employees", params={"category": "STRENGTH"})
    assert res.status_code == 404


# =====================================================================
# Quest detail (21-22)
# =====================================================================


def test_quest_detail_metrics(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Quest detail metrics")
    quest = _make_simple_quest(client, capability_ids["troubleshooting"], employee_id, title="Quest detail metrics quest", department_id=department_id)
    _complete_quest(client, quest["id"], employee_id)

    res = _quest_detail(client, quest["id"], department_id)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["attempts_completed"] == 1
    assert body["attempts_total"] == 1
    assert body["completion_rate"] == 1.0
    assert body["evaluation_criteria_count"] == 1


def test_quest_detail_capability_evidence_mapping(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Quest detail cap mapping")
    quest = _make_simple_quest(client, capability_ids["documentation"], employee_id, title="Quest detail cap mapping quest", department_id=department_id)
    _complete_quest(client, quest["id"], employee_id)

    body = _quest_detail(client, quest["id"], department_id).json()
    assert len(body["capability_breakdown"]) >= 1
    assert body["capability_breakdown"][0]["capability_key"] == "documentation"
    assert body["capability_breakdown"][0]["evidence_count"] > 0


def test_quest_detail_unknown_quest_404(client):
    res = _quest_detail(client, "does-not-exist")
    assert res.status_code == 404


# =====================================================================
# Security (23-27)
# =====================================================================


def test_security_no_evaluator_secrets_leaked(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Security employee")
    quest = _new_quest(client, department_id, title="6E security check quest")
    _add_task(client, quest["id"])
    _add_criterion(
        client,
        quest["id"],
        criterion_type="DETERMINISTIC",
        expected_answer="SECRET_6E_EXPECTED_ANSWER",
        expected_behavior="SECRET_6E_EXPECTED_BEHAVIOR",
        reference_solution="SECRET_6E_REFERENCE_SOLUTION",
    )
    _map_capability(client, quest["id"], capability_ids["troubleshooting"])
    _assign_employee(client, quest["id"], employee_id)
    _publish(client, quest["id"])
    _complete_quest(client, quest["id"], employee_id, solution="SECRET_6E_EXPECTED_ANSWER noted.")
    _next_quest(client, employee_id)

    endpoints = [
        "/api/v1/analytics/overview",
        "/api/v1/analytics/quests",
        f"/api/v1/analytics/quests/{quest['id']}",
        "/api/v1/analytics/capabilities",
        "/api/v1/analytics/development-signals",
        f"/api/v1/analytics/employees/{employee_id}",
        f"/api/v1/analytics/capabilities/{capability_ids['troubleshooting']}/employees?category=DEVELOPMENT_AREA",
    ]
    secrets = (
        "SECRET_6E_EXPECTED_ANSWER",
        "SECRET_6E_EXPECTED_BEHAVIOR",
        "SECRET_6E_REFERENCE_SOLUTION",
        "SECRET_6E_RAW_AI_RESPONSE",
    )
    hidden_field_names = (
        "expected_answer",
        "expected_behavior",
        "reference_solution",
        "raw_response",
        "prompt_version",
        "evaluation_version",
        "structured_result",
        "criterion_type",
        "max_score",
    )
    for endpoint in endpoints:
        text = client.get(endpoint).text
        for secret in secrets:
            assert secret not in text, f"{secret} leaked via {endpoint}"
        for field_name in hidden_field_names:
            assert field_name not in text, f"{field_name} leaked via {endpoint}"


# =====================================================================
# Edge cases (28-33)
# =====================================================================


def test_edge_case_no_employees_in_department(client, org_id):
    dept = client.post("/api/v1/departments", json={"organization_id": org_id, "name": "6E No Employees Dept"}).json()["id"]
    overview = _overview(client, dept)
    assert overview["employees_reached"] == 0
    assert overview["employees_with_capability_evidence"] == 0
    capabilities = _capability_analytics(client, dept)
    for row in capabilities["capabilities"]:
        assert row["total_employees"] == 0
        assert row["not_observed_employees"] == 0


def test_edge_case_no_quests_no_attempts(client, org_id):
    dept = client.post("/api/v1/departments", json={"organization_id": org_id, "name": "6E No Quests Dept"}).json()["id"]
    _new_employee(client, org_id, dept, name_prefix="No quests employee")
    overview = _overview(client, dept)
    assert overview["published_quests"] == 0
    assert overview["attempts_total"] == 0
    quests = _quest_analytics(client, dept)
    assert quests["quests"] == []


def test_edge_case_no_capability_evidence(client, org_id):
    dept = client.post("/api/v1/departments", json={"organization_id": org_id, "name": "6E No Evidence Dept"}).json()["id"]
    _new_employee(client, org_id, dept, name_prefix="No evidence employee")
    signals = _development_signals(client, dept)
    assert signals["development_areas"] == []


def test_edge_case_no_recommendations(client, org_id):
    dept = client.post("/api/v1/departments", json={"organization_id": org_id, "name": "6E No Recs Dept"}).json()["id"]
    overview = _overview(client, dept)
    assert overview["recommendations_generated"] == 0


def test_edge_case_department_with_no_activity(client, org_id):
    dept = client.post("/api/v1/departments", json={"organization_id": org_id, "name": "6E Inactive Dept"}).json()["id"]
    _new_employee(client, org_id, dept, name_prefix="Inactive dept employee")
    overview = _overview(client, dept)
    assert overview == {
        "department_id": dept,
        "published_quests": 0,
        "draft_quests": 0,
        "archived_quests": 0,
        "active_assignment_records": overview["active_assignment_records"],  # global, not department-scoped
        "employees_reached": 0,
        "attempts_total": 0,
        "attempts_not_started": 0,
        "attempts_in_progress": 0,
        "attempts_submitted": 0,
        "attempts_evaluating": 0,
        "attempts_completed": 0,
        "employees_with_capability_evidence": 0,
        "capability_observations": 0,
        "recommendations_generated": 0,
        "employees_with_development_history": 0,
        "recent_recommendations": [],  # this department has zero recommendations of its own
    }


# =====================================================================
# Read-only / no mutation, repeated GETs (Part 29)
# =====================================================================


def test_repeated_analytics_gets_do_not_mutate_database(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="No mutation employee")
    quest = _make_simple_quest(client, capability_ids["troubleshooting"], employee_id, title="No mutation quest", department_id=department_id)
    _complete_quest(client, quest["id"], employee_id)

    before = _quest_row_count()
    for _ in range(5):
        _overview(client, department_id)
        _quest_analytics(client, department_id)
        _quest_detail(client, quest["id"], department_id)
        _capability_analytics(client, department_id)
        _development_signals(client, department_id)
        _employee_analytics(client, employee_id)
    after = _quest_row_count()
    assert before == after


# =====================================================================
# Data integrity scenario (Part 29 full scenario)
# =====================================================================


def test_full_data_integrity_scenario(client, org_id, capability_ids):
    dept = client.post("/api/v1/departments", json={"organization_id": org_id, "name": "6E Integrity Dept"}).json()["id"]

    employee_a = _new_employee(client, org_id, dept, name_prefix="Integrity Employee A")
    employee_b = _new_employee(client, org_id, dept, name_prefix="Integrity Employee B")
    employee_c = _new_employee(client, org_id, dept, name_prefix="Integrity Employee C")

    quest_a = _make_simple_quest(client, capability_ids["troubleshooting"], employee_a, title="Integrity Quest A", department_id=dept)
    quest_b = _make_simple_quest(client, capability_ids["troubleshooting"], employee_a, title="Integrity Quest B", department_id=dept)
    quest_c = _make_simple_quest(client, capability_ids["documentation"], employee_b, title="Integrity Quest C", department_id=dept)

    _complete_quest(client, quest_a["id"], employee_a)
    rec = _next_quest(client, employee_a)
    assert rec["recommended_quest"]["id"] == quest_b["id"]

    _complete_quest(client, quest_c["id"], employee_b)

    # employee_c has no completed quest at all.

    row_counts_before = _quest_row_count()

    overview = _overview(client, dept)
    assert overview["published_quests"] == 3
    assert overview["attempts_completed"] == 2
    assert overview["recommendations_generated"] == 1
    assert overview["employees_with_capability_evidence"] == 2
    assert overview["employees_with_development_history"] == 2  # A and B; C has none

    capabilities = _capability_analytics(client, dept)["capabilities"]
    troubleshooting = next(c for c in capabilities if c["capability_key"] == "troubleshooting")
    documentation = next(c for c in capabilities if c["capability_key"] == "documentation")
    assert troubleshooting["development_area_employees"] == 1  # employee_a
    assert documentation["development_area_employees"] == 1  # employee_b
    assert troubleshooting["not_observed_employees"] == 2  # employee_b, employee_c
    assert documentation["not_observed_employees"] == 2  # employee_a, employee_c

    signals = _development_signals(client, dept)["development_areas"]
    signal_by_key = {s["capability_key"]: s["employee_count"] for s in signals}
    assert signal_by_key.get("troubleshooting") == 1
    assert signal_by_key.get("documentation") == 1

    employee_c_analytics = _employee_analytics(client, employee_c).json()
    assert employee_c_analytics["recent_quest_activity"] == []
    assert employee_c_analytics["latest_recommendation"] is None
    assert all(c["level"] == "NOT_OBSERVED" for c in employee_c_analytics["capabilities"])

    # Viewing analytics repeatedly must never mutate anything.
    for _ in range(3):
        _overview(client, dept)
        _quest_analytics(client, dept)
        _capability_analytics(client, dept)
        _development_signals(client, dept)
        _employee_analytics(client, employee_a)
        _employee_analytics(client, employee_b)
        _employee_analytics(client, employee_c)

    row_counts_after = _quest_row_count()
    assert row_counts_before == row_counts_after

    print(f"\n[Phase 6E integrity] department={dept}")
    print(f"  Quest/Attempt/Recommendation row counts stable at: {row_counts_after}")
    print(f"  Overview after scenario: {overview}")

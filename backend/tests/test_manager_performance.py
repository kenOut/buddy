"""Manager Performance & Readiness Visibility — Stage 1.

Covers GET /employees/{employee_id}/performance: admin-only auth
(never employee-session), mission/quest performance visibility, score/
pass/feedback exposure, capability level/evidence-count visibility, the
readiness summary + blocker list, and the trust boundary (no answer
keys, no raw AI output, no write path).

Runs against its own isolated SQLite file, same convention as every
other test_*.py module in this suite.
"""

import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_manager_performance.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Reassigned here, not just once at module import time — this
    # suite's own established fragility class (first diagnosed in
    # P2.1, recurring in P3/P4.1/the Correction phase): every test file
    # sets DATABASE_URL once at module top-level, but a module-scoped
    # fixture doesn't actually execute until pytest gets around to its
    # first test, by which point a later-collected file's own top-level
    # assignment may have already overwritten it. Reasserting
    # immediately before TestClient(...) triggers the real lifespan/
    # seed guarantees this file runs against its own isolated database
    # regardless of collection order.
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"
    with TestClient(app) as c:
        c.post("/api/v1/admin/login", json={"password": get_settings().admin_password})
        yield c
    TEST_DB_PATH.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _restore_database_url_after_each_test():
    """Restore whatever DATABASE_URL was active before this file's
    tests ran, so as not to leave a stale value for any test collected
    after this file."""
    original = os.environ.get("DATABASE_URL")
    yield
    if original is not None:
        os.environ["DATABASE_URL"] = original


@pytest.fixture(scope="module")
def demo_bundle(client):
    return client.get("/api/v1/onboarding/bundle/demo").json()


@pytest.fixture(scope="module")
def org_id(demo_bundle):
    return demo_bundle["employee"]["organization_id"]


@pytest.fixture(scope="module")
def department_id(demo_bundle):
    return demo_bundle["employee"]["department_id"]


@pytest.fixture(scope="module")
def capability_ids(client):
    caps = client.get("/api/v1/capabilities").json()
    return {c["key"]: c["id"] for c in caps}


def _create_employee(client, org_id, department_id, *, email, full_name="Performance Test Employee"):
    res = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department_id,
            "full_name": full_name,
            "email": email,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _new_employee_with_session(client, org_id, department_id, *, email, full_name="Session Employee"):
    """Provisions a real employee and issues + exchanges a real
    invitation, returning (employee_id, session_client) — the same
    pattern test_security_hardening.py already established for proving
    an employee session can't reach manager-only data."""
    employee_id = _create_employee(client, org_id, department_id, email=email, full_name=full_name)
    invitation = client.post(f"/api/v1/invitations/employees/{employee_id}/issue").json()

    session = TestClient(app)
    exchange = session.post("/api/v1/invitations/exchange", json={"token": invitation["token"]})
    assert exchange.status_code == 200, exchange.text
    return employee_id, session


def _create_mission(client, department_id, *, title, workspace_type="reflection", required=False):
    res = client.post(
        "/api/v1/missions",
        json={
            "department_id": department_id,
            "title": title,
            "mission_type": "task",
            "workspace_type": workspace_type,
            "required": required,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _build_and_publish_quest(
    client,
    employee_id,
    capability_ids,
    *,
    title,
    required=False,
    expected_answer="checkout-service",
):
    quest = client.post(
        "/api/v1/quests",
        json={
            "title": title,
            "description": "A real workplace problem for manager-performance tests.",
            "quest_type": "INVESTIGATE",
            "workspace_type": "INVESTIGATION",
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
    client.post(
        f"/api/v1/quests/{qid}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee_id, "required": required},
    )
    pub = client.post(f"/api/v1/quests/{qid}/publish")
    assert pub.status_code == 200, pub.text
    return qid


def _submit_and_evaluate_quest(client, quest_id, employee_id, *, solution_text):
    attempt = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest_id, "employee_id": employee_id}
    ).json()
    aid = attempt["id"]
    client.patch(
        f"/api/v1/quest-attempts/{aid}",
        json={
            "employee_id": employee_id,
            "findings": "Latency spiked sharply on the relevant service.",
            "reasoning": "Timing lines up with a recent deploy that introduced a slow query.",
            "solution": solution_text,
        },
    )
    submit = client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": employee_id})
    assert submit.status_code == 200, submit.text
    evaluate = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": employee_id})
    assert evaluate.status_code == 200, evaluate.text
    return aid


# =====================================================================
# Fixture: a richly-populated employee — completed/failed/in-progress
# missions, completed/in-progress quests, one required-and-incomplete
# item of each kind, capability evidence from the completed quest.
# =====================================================================


@pytest.fixture(scope="module")
def perf_department_id(client, org_id):
    res = client.post(
        "/api/v1/departments", json={"organization_id": org_id, "name": "Manager Performance Test Dept"}
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


@pytest.fixture(scope="module")
def perf_setup(client, org_id, perf_department_id, capability_ids):
    # Missions created BEFORE the employee exists — mission assignments
    # are provisioned once, at the employee's first bundle fetch (P2 —
    # Provisioning Boundary).
    reflection_required_id = _create_mission(
        client, perf_department_id, title="Meet your onboarding buddy", workspace_type="reflection", required=True
    )
    investigation_required_id = _create_mission(
        client,
        perf_department_id,
        title="Diagnose the checkout latency spike",
        workspace_type="investigation",
        required=True,
    )
    quiz_optional_id = _create_mission(
        client, perf_department_id, title="Read the on-call handbook", workspace_type="quiz", required=False
    )

    employee_id = _create_employee(
        client, org_id, perf_department_id, email="perf-employee@kowri.test", full_name="Performance Employee"
    )
    client.get(f"/api/v1/onboarding/bundle/{employee_id}")  # provisions mission assignments

    # Reflection mission: passed, scored 100.
    reflection_attempt = client.post(
        "/api/v1/mission-attempts", json={"mission_id": reflection_required_id, "employee_id": employee_id}
    ).json()
    submit = client.post(
        f"/api/v1/mission-attempts/{reflection_attempt['id']}/submit",
        json={
            "employee_id": employee_id,
            "reasoning": "Talked through team norms and the on-call rotation with my buddy.",
        },
    )
    assert submit.status_code == 200, submit.text
    assert submit.json()["passed"] is True

    # Investigation mission: wrong answer, fails, stays "submitted" (retryable).
    investigation_attempt = client.post(
        "/api/v1/mission-attempts", json={"mission_id": investigation_required_id, "employee_id": employee_id}
    ).json()
    fail_submit = client.post(
        f"/api/v1/mission-attempts/{investigation_attempt['id']}/submit",
        json={
            "employee_id": employee_id,
            "affected_service": "payments-service",
            "likely_cause": "Payments provider outage",
            "reasoning": "A guess, not backed by the evidence.",
            "evidence_viewed": [],
        },
    )
    assert fail_submit.status_code == 200, fail_submit.text
    assert fail_submit.json()["passed"] is False

    # Quiz mission: started (in_progress), never submitted — no score yet.
    client.post("/api/v1/mission-attempts", json={"mission_id": quiz_optional_id, "employee_id": employee_id})

    # Quest 1: required, completed, correct answer -> passed, score 100,
    # capability evidence created (deterministic + AI, both source
    # "troubleshooting").
    quest_required_id = _build_and_publish_quest(
        client, employee_id, capability_ids, title="Required investigation quest", required=True
    )
    _submit_and_evaluate_quest(
        client, quest_required_id, employee_id, solution_text="checkout-service needs a rollback."
    )

    # Quest 2: optional, attempt created and autosaved, never submitted
    # -> IN_PROGRESS, no score.
    quest_optional_id = _build_and_publish_quest(
        client, employee_id, capability_ids, title="Optional investigation quest", required=False
    )
    attempt2 = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest_optional_id, "employee_id": employee_id}
    ).json()
    client.patch(
        f"/api/v1/quest-attempts/{attempt2['id']}",
        json={"employee_id": employee_id, "findings": "Still looking into this."},
    )

    return {
        "employee_id": employee_id,
        "reflection_mission_id": reflection_required_id,
        "investigation_mission_id": investigation_required_id,
        "quiz_mission_id": quiz_optional_id,
        "quest_required_id": quest_required_id,
        "quest_optional_id": quest_optional_id,
    }


@pytest.fixture(scope="module")
def perf_response(client, perf_setup):
    res = client.get(f"/api/v1/employees/{perf_setup['employee_id']}/performance")
    assert res.status_code == 200, res.text
    return res.json()


# =====================================================================
# Authorization
# =====================================================================


def test_anonymous_request_is_rejected(perf_setup):
    anon = TestClient(app)
    res = anon.get(f"/api/v1/employees/{perf_setup['employee_id']}/performance")
    assert res.status_code == 401


def test_employee_session_is_rejected(client, org_id, perf_department_id, perf_setup):
    _, employee_session = _new_employee_with_session(
        client, org_id, perf_department_id, email="perf-outsider@kowri.test"
    )
    res = employee_session.get(f"/api/v1/employees/{perf_setup['employee_id']}/performance")
    assert res.status_code == 401


def test_admin_session_is_allowed(perf_response):
    assert perf_response["employee"]["id"]


# =====================================================================
# Employee retrieval
# =====================================================================


def test_existing_employee_returns_performance(perf_response, perf_setup):
    assert perf_response["employee"]["id"] == perf_setup["employee_id"]
    assert perf_response["employee"]["full_name"] == "Performance Employee"


def test_unknown_employee_returns_404(client):
    res = client.get("/api/v1/employees/does-not-exist/performance")
    assert res.status_code == 404


# =====================================================================
# Mission performance
# =====================================================================


def _mission_by_id(perf_response, mission_id):
    return next(m for m in perf_response["missions"] if m["id"] == mission_id)


def test_completed_mission_with_score(perf_response, perf_setup):
    m = _mission_by_id(perf_response, perf_setup["reflection_mission_id"])
    assert m["assignment_status"] == "completed"
    assert m["attempt_status"] == "completed"
    assert m["score"] == 100.0
    assert m["passed"] is True
    assert m["feedback"]


def test_in_progress_mission_without_score(perf_response, perf_setup):
    m = _mission_by_id(perf_response, perf_setup["quiz_mission_id"])
    assert m["attempt_status"] == "in_progress"
    assert m["score"] is None
    assert m["passed"] is None


def test_failed_mission(perf_response, perf_setup):
    m = _mission_by_id(perf_response, perf_setup["investigation_mission_id"])
    assert m["attempt_status"] == "submitted"
    assert m["passed"] is False
    assert m["score"] == 0.0


def test_required_mission_flagged(perf_response, perf_setup):
    m = _mission_by_id(perf_response, perf_setup["reflection_mission_id"])
    assert m["required"] is True


def test_optional_mission_flagged(perf_response, perf_setup):
    m = _mission_by_id(perf_response, perf_setup["quiz_mission_id"])
    assert m["required"] is False


# =====================================================================
# Quest performance
# =====================================================================


def _quest_by_id(perf_response, quest_id):
    return next(q for q in perf_response["quests"] if q["id"] == quest_id)


def test_completed_quest_with_score(perf_response, perf_setup):
    q = _quest_by_id(perf_response, perf_setup["quest_required_id"])
    assert q["attempt_status"] == "COMPLETED"
    assert q["score"] == 100.0
    assert q["passed"] is True


def test_in_progress_quest(perf_response, perf_setup):
    q = _quest_by_id(perf_response, perf_setup["quest_optional_id"])
    assert q["attempt_status"] in ("IN_PROGRESS", "NOT_STARTED")
    assert q["score"] is None


def test_required_quest_flagged(perf_response, perf_setup):
    q = _quest_by_id(perf_response, perf_setup["quest_required_id"])
    assert q["required"] is True


def test_optional_quest_flagged(perf_response, perf_setup):
    q = _quest_by_id(perf_response, perf_setup["quest_optional_id"])
    assert q["required"] is False


# =====================================================================
# Capability
# =====================================================================


def test_capability_levels_included(perf_response):
    assert perf_response["capabilities"], "expected at least one capability profile"
    troubleshooting = next(
        c for c in perf_response["capabilities"] if c["capability_key"] == "troubleshooting"
    )
    assert troubleshooting["level"] in ("NOT_OBSERVED", "DEVELOPING", "CAPABLE", "STRONG")


def test_capability_evidence_counts_included(perf_response):
    troubleshooting = next(
        c for c in perf_response["capabilities"] if c["capability_key"] == "troubleshooting"
    )
    assert troubleshooting["evidence_count"] >= 1
    assert isinstance(troubleshooting["confidence"], float)


_FORBIDDEN_KEYS = {
    "expected_answer",
    "expected_behavior",
    "reference_solution",
    "correct_service",
    "correct_cause",
    "correct_option",
    "raw_response",
    "prompt_version",
    "evaluation_version",
}


def _walk(obj):
    if isinstance(obj, dict):
        yield from obj.keys()
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item)


def test_no_raw_evaluation_internals_exposed(perf_response):
    keys_present = set(_walk(perf_response))
    assert not (keys_present & _FORBIDDEN_KEYS), keys_present & _FORBIDDEN_KEYS


# =====================================================================
# Readiness
# =====================================================================


def test_not_ready_employee(perf_response):
    assert perf_response["readiness"]["ready"] is False


def test_ready_employee(client, org_id, capability_ids):
    """A separate, deliberately minimal employee IN ITS OWN DEPARTMENT
    (not perf_department_id, which by this point in the module already
    has other required missions from other fixtures — sharing it would
    mean this employee inherits those as required-but-incomplete too,
    since Mission assignments are auto-provisioned at employee-creation
    time for every Mission that already exists in the department):
    exactly one required mission (passed), one required quest (completed
    + passed), onboarding driven to completion — enough to actually
    satisfy readiness_service's unmodified predicate."""
    dept = client.post(
        "/api/v1/departments", json={"organization_id": org_id, "name": "Ready Path Test Dept"}
    )
    assert dept.status_code == 201, dept.text
    ready_department_id = dept.json()["id"]

    mission_id = _create_mission(
        client, ready_department_id, title="Ready-path mission", workspace_type="reflection", required=True
    )
    employee_id = _create_employee(
        client, org_id, ready_department_id, email="perf-ready@kowri.test", full_name="Ready Employee"
    )
    bundle = client.get(f"/api/v1/onboarding/bundle/{employee_id}").json()
    session_id = bundle["session"]["id"]

    attempt = client.post(
        "/api/v1/mission-attempts", json={"mission_id": mission_id, "employee_id": employee_id}
    ).json()
    client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/submit",
        json={"employee_id": employee_id, "reasoning": "A genuine, specific description of the work done."},
    )

    quest_id = _build_and_publish_quest(
        client, employee_id, capability_ids, title="Ready-path quest", required=True
    )
    _submit_and_evaluate_quest(client, quest_id, employee_id, solution_text="checkout-service needs a rollback.")

    complete = client.patch(
        f"/api/v1/onboarding/sessions/{session_id}", json={"current_scene": "completion"}
    )
    assert complete.status_code == 200, complete.text

    res = client.get(f"/api/v1/employees/{employee_id}/performance")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["readiness"]["ready"] is True
    assert body["readiness"]["blockers"] == []


def test_readiness_blockers_returned(perf_response):
    blockers = perf_response["readiness"]["blockers"]
    assert blockers, "expected at least one blocker for a not-ready employee"
    assert any("Diagnose the checkout latency spike" in b for b in blockers)
    assert any("Onboarding" in b for b in blockers)


# =====================================================================
# Score integrity
# =====================================================================


def test_endpoint_has_no_write_path(client, perf_setup):
    res = client.post(f"/api/v1/employees/{perf_setup['employee_id']}/performance", json={"score": 100})
    assert res.status_code == 405


def test_answer_keys_absent_from_response(perf_response):
    import json

    blob = json.dumps(perf_response)
    for leaked in ("checkout-service is the answer", "payments-service outage", "correct_option"):
        assert leaked not in blob


# =====================================================================
# Edge cases — a bare employee with nothing assigned at all
# =====================================================================


@pytest.fixture(scope="module")
def bare_response(client, org_id):
    # A dedicated, empty department — not perf_department_id, which
    # already has missions/quests from other fixtures by this point in
    # the module (any employee created in that department would inherit
    # those as real assignments, since Mission assignment provisioning
    # is eager at employee-creation time).
    dept = client.post(
        "/api/v1/departments", json={"organization_id": org_id, "name": "Bare Employee Test Dept"}
    )
    assert dept.status_code == 201, dept.text
    bare_department_id = dept.json()["id"]

    employee_id = _create_employee(
        client, org_id, bare_department_id, email="perf-bare@kowri.test", full_name="Bare Employee"
    )
    res = client.get(f"/api/v1/employees/{employee_id}/performance")
    assert res.status_code == 200, res.text
    return res.json()


def test_no_missions(bare_response):
    assert bare_response["missions"] == []
    assert bare_response["performance_summary"]["missions_assigned"] == 0


def test_no_quests(bare_response):
    assert bare_response["quests"] == []
    assert bare_response["performance_summary"]["quests_assigned"] == 0


def test_no_capability_evidence(bare_response):
    assert bare_response["capabilities"] == []


def test_no_scored_attempts(bare_response):
    assert bare_response["performance_summary"]["scored_items"] == 0
    assert bare_response["performance_summary"]["average_score"] is None

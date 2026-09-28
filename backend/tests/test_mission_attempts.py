"""Stage 3 backend tests for the mission attempt API.

Runs against an isolated SQLite file (separate from test_onboarding_fixes.py's),
deleted and recreated each run.
"""

import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_mission_attempts.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.config import get_settings  # noqa: E402

MISSION_TITLE = "Diagnose the checkout latency spike"
CORRECT_SERVICE = "checkout-service"
CORRECT_CAUSE = "New deploy introduced a query that exhausts the DB connection pool"
WRONG_SERVICE = "payments-service"
WRONG_CAUSE = "Payments provider outage"


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
def org_id(client):
    bundle = client.get("/api/v1/onboarding/bundle/demo").json()
    return bundle["employee"]["organization_id"]


@pytest.fixture(scope="module")
def department_id(client):
    # Same department as the demo employee — so a mission_id looked up
    # from the demo bundle is also assignable to a freshly-created
    # employee in these tests (Mission assignment provisioning is
    # department-scoped; see mission_service.ensure_assignments_for_employee).
    bundle = client.get("/api/v1/onboarding/bundle/demo").json()
    return bundle["employee"]["department_id"]


@pytest.fixture(scope="module")
def mission_id(client, demo_employee_id):
    missions = client.get(f"/api/v1/employees/{demo_employee_id}/missions").json()
    matches = [m for m in missions if m["mission"]["title"] == MISSION_TITLE]
    assert matches, "seeded investigation mission not found"
    return matches[0]["mission_id"]


@pytest.fixture(scope="module")
def reflection_mission_id(client, demo_employee_id):
    # Fetching the bundle provisions/returns mission_assignments, including
    # the reflection-workspace missions — same source the real
    # employee-facing MissionWorkspace reads from.
    bundle = client.get(f"/api/v1/onboarding/bundle/{demo_employee_id}").json()
    match = next(
        a for a in bundle["mission_assignments"] if a["mission"]["title"] == "Meet your onboarding buddy"
    )
    assert match["status"] == "pending"
    assert match["mission"]["workspace_type"] == "reflection"
    return match["mission_id"]


@pytest.fixture(scope="module")
def quiz_mission_id(client, demo_employee_id):
    bundle = client.get(f"/api/v1/onboarding/bundle/{demo_employee_id}").json()
    match = next(
        a for a in bundle["mission_assignments"] if a["mission"]["title"] == "Read the on-call handbook"
    )
    assert match["mission"]["workspace_type"] == "quiz"
    return match["mission_id"]


@pytest.fixture(scope="module")
def unassigned_employee_id(client):
    # An employee whose bundle/session was never fetched — no
    # mission_assignments have been provisioned for them at all.
    employees = client.get("/api/v1/employees").json()
    other = next(e for e in employees if e["email"] == "ama.asante@buddy.dev")
    return other["id"]


@pytest.fixture(scope="module")
def assigned_but_not_started_employee_id(client):
    # Fetching the bundle provisions mission_assignments (ownership exists),
    # but no mission_attempt has been created for them yet.
    employees = client.get("/api/v1/employees").json()
    david = next(e for e in employees if e["email"] == "david.owusu@buddy.dev")
    client.get(f"/api/v1/onboarding/bundle/{david['id']}")  # provisions assignments
    return david["id"]


# ---- scenario retrieval ----


def test_valid_mission_scenario_retrieval(client, mission_id, demo_employee_id):
    res = client.get(f"/api/v1/missions/{mission_id}/scenario?employee_id={demo_employee_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["briefing"]
    assert len(body["metrics"]) > 0
    assert len(body["logs"]) > 0
    assert len(body["services"]) > 0
    assert len(body["timeline"]) > 0
    assert CORRECT_SERVICE in body["service_options"]
    assert CORRECT_CAUSE in body["cause_options"]
    # answer key must never leave the server
    assert "correct_service" not in body
    assert "correct_cause" not in body


def test_invalid_mission_id_is_not_found(client, demo_employee_id):
    res = client.get(f"/api/v1/missions/does-not-exist/scenario?employee_id={demo_employee_id}")
    assert res.status_code == 404


def test_unassigned_mission_is_rejected(client, mission_id, unassigned_employee_id):
    res = client.get(f"/api/v1/missions/{mission_id}/scenario?employee_id={unassigned_employee_id}")
    assert res.status_code == 403


# ---- attempt lifecycle ----


def test_attempt_creation(client, mission_id, demo_employee_id):
    res = client.post(
        "/api/v1/mission-attempts", json={"mission_id": mission_id, "employee_id": demo_employee_id}
    )
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "in_progress"
    assert body["started_at"] is not None
    assert body["mission_id"] == mission_id


def test_attempt_creation_is_idempotent_no_duplicate(client, mission_id, demo_employee_id):
    first = client.post(
        "/api/v1/mission-attempts", json={"mission_id": mission_id, "employee_id": demo_employee_id}
    ).json()
    second = client.post(
        "/api/v1/mission-attempts", json={"mission_id": mission_id, "employee_id": demo_employee_id}
    ).json()
    assert first["id"] == second["id"]


def test_attempt_creation_rejects_unassigned_mission(client, mission_id, unassigned_employee_id):
    res = client.post(
        "/api/v1/mission-attempts",
        json={"mission_id": mission_id, "employee_id": unassigned_employee_id},
    )
    assert res.status_code == 403


def test_attempt_retrieval(client, mission_id, demo_employee_id):
    res = client.get(
        f"/api/v1/mission-attempts?mission_id={mission_id}&employee_id={demo_employee_id}"
    )
    assert res.status_code == 200
    assert res.json()["mission_id"] == mission_id


def test_attempt_retrieval_rejects_unassigned_mission(client, mission_id, unassigned_employee_id):
    # unassigned -> ownership check fails first, 403 not 404
    res = client.get(
        f"/api/v1/mission-attempts?mission_id={mission_id}&employee_id={unassigned_employee_id}"
    )
    assert res.status_code == 403


def test_attempt_retrieval_not_started_is_not_found(
    client, mission_id, assigned_but_not_started_employee_id
):
    # assigned, but no attempt created yet -> genuine 404, distinct from
    # the 403 ownership case above.
    res = client.get(
        f"/api/v1/mission-attempts?mission_id={mission_id}"
        f"&employee_id={assigned_but_not_started_employee_id}"
    )
    assert res.status_code == 404


def test_attempt_update_and_resume_merges_evidence(client, mission_id, demo_employee_id):
    attempt = client.post(
        "/api/v1/mission-attempts", json={"mission_id": mission_id, "employee_id": demo_employee_id}
    ).json()
    attempt_id = attempt["id"]

    first = client.patch(
        f"/api/v1/mission-attempts/{attempt_id}",
        json={"affected_service": CORRECT_SERVICE, "evidence_viewed": ["metrics:m1"]},
    ).json()
    assert first["affected_service"] == CORRECT_SERVICE
    assert first["evidence_viewed"] == ["metrics:m1"]

    # Simulate leaving and returning: partial update again, evidence merges
    # rather than replaces (resume must not lose prior progress).
    second = client.patch(
        f"/api/v1/mission-attempts/{attempt_id}",
        json={"reasoning": "The connection pool is saturated.", "evidence_viewed": ["logs:l1"]},
    ).json()
    assert second["affected_service"] == CORRECT_SERVICE  # preserved from before
    assert set(second["evidence_viewed"]) == {"metrics:m1", "logs:l1"}
    assert second["reasoning"] == "The connection pool is saturated."

    # Resuming (re-fetching) shows the same persisted state, not a reset.
    resumed = client.get(
        f"/api/v1/mission-attempts?mission_id={mission_id}&employee_id={demo_employee_id}"
    ).json()
    assert resumed["id"] == attempt_id
    assert resumed["affected_service"] == CORRECT_SERVICE
    assert set(resumed["evidence_viewed"]) == {"metrics:m1", "logs:l1"}


# ---- submission + evaluation ----


def test_unsuccessful_submission(client, mission_id, demo_employee_id):
    attempt = client.get(
        f"/api/v1/mission-attempts?mission_id={mission_id}&employee_id={demo_employee_id}"
    ).json()

    res = client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/submit",
        json={
            "employee_id": demo_employee_id,
            "affected_service": WRONG_SERVICE,
            "likely_cause": WRONG_CAUSE,
            "reasoning": "I think it's the payments provider.",
            "evidence_viewed": ["metrics:m1"],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["passed"] is False
    assert body["score"] == 0.0
    assert body["status"] == "submitted"
    assert body["feedback"]
    assert "correct_service" not in body
    assert "correct_cause" not in body


def test_successful_submission_after_revising(client, mission_id, demo_employee_id):
    attempt = client.get(
        f"/api/v1/mission-attempts?mission_id={mission_id}&employee_id={demo_employee_id}"
    ).json()

    res = client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/submit",
        json={
            "employee_id": demo_employee_id,
            "affected_service": CORRECT_SERVICE,
            "likely_cause": CORRECT_CAUSE,
            "reasoning": "The new deploy added a query that saturated the DB connection pool.",
            "evidence_viewed": ["metrics:m1", "metrics:m4", "logs:l1", "timeline:t1"],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["passed"] is True
    assert body["score"] == 100.0
    assert body["status"] == "completed"
    assert body["completed_at"] is not None


def test_duplicate_submission_after_completion_is_rejected(client, mission_id, demo_employee_id):
    attempt = client.get(
        f"/api/v1/mission-attempts?mission_id={mission_id}&employee_id={demo_employee_id}"
    ).json()
    assert attempt["status"] == "completed"

    res = client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/submit",
        json={
            "employee_id": demo_employee_id,
            "affected_service": CORRECT_SERVICE,
            "likely_cause": CORRECT_CAUSE,
            "reasoning": "Resubmitting.",
            "evidence_viewed": [],
        },
    )
    assert res.status_code == 409


def test_mission_assignment_reflects_completion(client, mission_id, demo_employee_id):
    missions = client.get(f"/api/v1/employees/{demo_employee_id}/missions").json()
    match = next(m for m in missions if m["mission_id"] == mission_id)
    assert match["status"] == "completed"


# ---- reflection/quiz mission completion (via the same attempt/submit
# flow every workspace type uses — see mission_attempt_service.py) ----
#
# The old bare "PATCH /mission-assignments/{id} {status: completed}"
# shortcut is gone entirely: every mission now requires real submitted
# work, graded through submit_attempt, before its assignment can reach
# "completed". These tests exercise that same open (non-admin-gated)
# mission_attempts.router path the removed endpoint used to.

QUIZ_ANSWERS = {
    "q1": "Acknowledge the page and start reading the runbook linked in the alert",
    "q2": "Sev-1 is customer-facing and actively losing money or data; Sev-3 is degraded but contained",
    "q3": "If you haven't made progress within the escalation window, or the incident is outside your area",
}


def test_reflection_mission_can_be_completed_by_its_own_employee(
    client, reflection_mission_id, demo_employee_id
):
    attempt = client.post(
        "/api/v1/mission-attempts",
        json={"mission_id": reflection_mission_id, "employee_id": demo_employee_id},
    ).json()
    res = client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/submit",
        json={
            "employee_id": demo_employee_id,
            "reasoning": "I spent 15 minutes with my buddy and asked about team norms, on-call rotation, "
            "and how code review works here.",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["passed"] is True
    assert body["status"] == "completed"
    assert body["completed_at"] is not None

    missions = client.get(f"/api/v1/employees/{demo_employee_id}/missions").json()
    match = next(m for m in missions if m["mission_id"] == reflection_mission_id)
    assert match["status"] == "completed"


def test_reflection_mission_submission_rejects_a_different_employee(
    client, reflection_mission_id, demo_employee_id, unassigned_employee_id
):
    attempt = client.post(
        "/api/v1/mission-attempts",
        json={"mission_id": reflection_mission_id, "employee_id": demo_employee_id},
    ).json()
    res = client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/submit",
        json={"employee_id": unassigned_employee_id, "reasoning": "Not my mission to submit."},
    )
    assert res.status_code == 403


def test_reflection_mission_requires_a_substantive_submission(client, demo_employee_id, org_id, department_id):
    # A separate employee so this doesn't collide with the module-scoped
    # reflection_mission_id fixture's own attempt.
    employee = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department_id,
            "full_name": "Reflection Threshold Employee",
            "email": "reflection-threshold@kowri.test",
        },
    ).json()
    bundle = client.get(f"/api/v1/onboarding/bundle/{employee['id']}").json()  # provisions assignments
    mission_id = next(
        a for a in bundle["mission_assignments"] if a["mission"]["title"] == "Meet your onboarding buddy"
    )["mission_id"]

    attempt = client.post(
        "/api/v1/mission-attempts", json={"mission_id": mission_id, "employee_id": employee["id"]}
    ).json()
    res = client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/submit",
        json={"employee_id": employee["id"], "reasoning": "Did it."},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["passed"] is False
    assert body["status"] == "submitted"


def test_missing_mission_attempt_submit_is_not_found(client, demo_employee_id):
    res = client.post(
        "/api/v1/mission-attempts/does-not-exist/submit",
        json={"employee_id": demo_employee_id, "reasoning": "..."},
    )
    assert res.status_code == 404


def test_quiz_mission_can_be_completed_by_its_own_employee(client, quiz_mission_id, demo_employee_id):
    attempt = client.post(
        "/api/v1/mission-attempts",
        json={"mission_id": quiz_mission_id, "employee_id": demo_employee_id},
    ).json()
    res = client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/submit",
        json={"employee_id": demo_employee_id, "quiz_answers": QUIZ_ANSWERS},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["passed"] is True
    assert body["score"] == 100.0

    missions = client.get(f"/api/v1/employees/{demo_employee_id}/missions").json()
    match = next(m for m in missions if m["mission_id"] == quiz_mission_id)
    assert match["status"] == "completed"


def test_quiz_mission_with_wrong_answers_does_not_pass(client, demo_employee_id, org_id, department_id):
    employee = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department_id,
            "full_name": "Quiz Threshold Employee",
            "email": "quiz-threshold@kowri.test",
        },
    ).json()
    bundle = client.get(f"/api/v1/onboarding/bundle/{employee['id']}").json()  # provisions assignments
    mission_id = next(
        a for a in bundle["mission_assignments"] if a["mission"]["title"] == "Read the on-call handbook"
    )["mission_id"]

    attempt = client.post(
        "/api/v1/mission-attempts", json={"mission_id": mission_id, "employee_id": employee["id"]}
    ).json()
    res = client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/submit",
        json={"employee_id": employee["id"], "quiz_answers": {"q1": "wrong", "q2": "wrong", "q3": "wrong"}},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["passed"] is False
    assert body["score"] == 0.0


def test_reflection_mission_completion_requires_no_admin_session(client, demo_employee_id, org_id, department_id):
    # Drop the admin session cookie for one call — proves this path is
    # reachable by a real (non-admin) employee. No new app/lifespan/DB
    # involved, just the same shared client with its cookie temporarily
    # withheld.
    employee = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department_id,
            "full_name": "No Admin Session Employee",
            "email": "no-admin-session-mission@kowri.test",
        },
    ).json()
    bundle = client.get(f"/api/v1/onboarding/bundle/{employee['id']}").json()
    mission_id = next(
        a for a in bundle["mission_assignments"] if a["mission"]["title"] == "Meet your onboarding buddy"
    )["mission_id"]

    saved_cookie = client.cookies.get("buddy_admin_session")
    del client.cookies["buddy_admin_session"]
    try:
        attempt = client.post(
            "/api/v1/mission-attempts", json={"mission_id": mission_id, "employee_id": employee["id"]}
        ).json()
        res = client.post(
            f"/api/v1/mission-attempts/{attempt['id']}/submit",
            json={
                "employee_id": employee["id"],
                "reasoning": "We talked through the team's on-call rotation and how sprint planning works.",
            },
        )
    finally:
        client.cookies.set("buddy_admin_session", saved_cookie)
    assert res.status_code == 200
    assert res.json()["passed"] is True

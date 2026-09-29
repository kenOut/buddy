"""Manager Portal login — the auth boundary itself: unauthenticated
requests to admin-only routes are rejected, a correct password
establishes a session, an incorrect one doesn't, logout tears the
session down, and none of this touches the employee-facing/onboarding
surface, which must stay fully open with zero login required.

Runs against its own isolated SQLite file, per this project's convention.
"""

import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_admin_auth.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.config import get_settings  # noqa: E402


@pytest.fixture(scope="module")
def anon_client():
    """Deliberately never logs in — every test in this file that checks
    unauthenticated behavior uses this, never the module's `client`."""
    with TestClient(app) as c:
        yield c
    TEST_DB_PATH.unlink(missing_ok=True)


# =====================================================================
# Gated routes reject unauthenticated requests
# =====================================================================


def test_admin_overview_requires_login(anon_client):
    res = anon_client.get("/api/v1/admin/overview")
    assert res.status_code == 401


def test_analytics_overview_requires_login(anon_client):
    res = anon_client.get("/api/v1/analytics/overview")
    assert res.status_code == 401


def test_employees_list_requires_login(anon_client):
    res = anon_client.get("/api/v1/employees")
    assert res.status_code == 401


def test_departments_create_requires_login(anon_client):
    res = anon_client.post("/api/v1/departments", json={"organization_id": "x", "name": "y"})
    assert res.status_code == 401


def test_quest_create_requires_login(anon_client):
    """The mixed router — only the admin-authoring handlers are gated."""
    res = anon_client.post(
        "/api/v1/quests",
        json={"title": "t", "quest_type": "OTHER", "workspace_type": "GENERAL"},
    )
    assert res.status_code == 401


def test_quest_list_requires_login(anon_client):
    res = anon_client.get("/api/v1/quests")
    assert res.status_code == 401


def test_quest_task_create_requires_login(anon_client):
    res = anon_client.post("/api/v1/quests/nonexistent/tasks", json={"title": "t", "task_type": "OTHER"})
    assert res.status_code == 401


def test_quest_assignment_create_requires_login(anon_client):
    res = anon_client.post(
        "/api/v1/quests/nonexistent/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": "x"},
    )
    assert res.status_code == 401


def test_quest_assignment_required_update_requires_login(anon_client):
    """Phase 8H-3 (launch-audit follow-up): setting `required` goes
    through the same PATCH endpoint every other assignment edit already
    does — this proves that stays true for the new field specifically,
    not just for `active`."""
    res = anon_client.patch(
        "/api/v1/quests/nonexistent/assignments/nonexistent", json={"required": True}
    )
    assert res.status_code == 401


def test_missions_create_requires_login(anon_client):
    res = anon_client.post("/api/v1/missions", json={"title": "t", "mission_type": "task"})
    assert res.status_code == 401


def test_onboarding_bundle_by_employee_id_requires_login(anon_client):
    """P1 (launch-audit follow-up): this route used to be fully open to
    any caller who supplied an employee_id — a cross-employee data
    exposure. See test_employee_invitations.py for the full identity/
    invitation/session surface this phase adds."""
    bundle = anon_client.get("/api/v1/onboarding/bundle/demo").json()
    res = anon_client.get(f"/api/v1/onboarding/bundle/{bundle['employee']['id']}")
    assert res.status_code == 401


def test_invitation_issue_requires_login(anon_client):
    bundle = anon_client.get("/api/v1/onboarding/bundle/demo").json()
    res = anon_client.post(f"/api/v1/invitations/employees/{bundle['employee']['id']}/issue")
    assert res.status_code == 401


def test_invitation_resend_requires_login(anon_client):
    """P3 — Email Provider Foundation."""
    bundle = anon_client.get("/api/v1/onboarding/bundle/demo").json()
    res = anon_client.post(f"/api/v1/invitations/employees/{bundle['employee']['id']}/resend")
    assert res.status_code == 401


# =====================================================================
# Employee-facing / onboarding surface stays fully open, no login at all
# =====================================================================


def test_onboarding_bundle_never_requires_login(anon_client):
    res = anon_client.get("/api/v1/onboarding/bundle/demo")
    assert res.status_code == 200


def test_invitation_exchange_never_requires_login(anon_client):
    """The employee-facing entry point — there is no session yet at this
    point in the flow. A 401 here means "bad token", not "please log
    in" (see test_employee_invitations.py for that distinction)."""
    res = anon_client.post("/api/v1/invitations/exchange", json={"token": "whatever"})
    assert res.status_code == 401
    assert isinstance(res.json()["detail"], dict)


def test_capabilities_list_never_requires_login(anon_client):
    res = anon_client.get("/api/v1/capabilities")
    assert res.status_code == 200


def test_employee_quest_eligibility_never_requires_login(anon_client):
    """The mixed router's employee-facing handlers must NOT be gated —
    a 404 (quest doesn't exist) here, not a 401, proves the request was
    let through to actual business logic rather than rejected at the
    auth boundary."""
    res = anon_client.get(
        "/api/v1/quests/nonexistent-quest/eligibility/nonexistent-employee"
    )
    assert res.status_code == 404


def test_quest_attempt_create_never_requires_login(anon_client):
    res = anon_client.post(
        "/api/v1/quest-attempts", json={"quest_id": "nonexistent", "employee_id": "nonexistent"}
    )
    assert res.status_code == 404


def test_mission_attempts_list_never_requires_login(anon_client):
    """Requires both mission_id and employee_id; a nonexistent mission_id
    proves the request reached real business logic (404 from
    _assert_owns_mission) rather than being rejected at the auth boundary
    (401) — same pattern as the quest-eligibility check above."""
    bundle = anon_client.get("/api/v1/onboarding/bundle/demo").json()
    res = anon_client.get(
        "/api/v1/mission-attempts",
        params={"mission_id": "nonexistent-mission", "employee_id": bundle["employee"]["id"]},
    )
    assert res.status_code == 404


def test_development_journey_never_requires_login(anon_client):
    """Shared between onboarding and the admin employee-journey page —
    must stay open (gating it would break the employee-facing flow)."""
    bundle = anon_client.get("/api/v1/onboarding/bundle/demo").json()
    res = anon_client.get(f"/api/v1/employees/{bundle['employee']['id']}/development-journey")
    assert res.status_code == 200


# =====================================================================
# Login / logout / session lifecycle
# =====================================================================


def test_login_with_wrong_password_fails(anon_client):
    res = anon_client.post("/api/v1/admin/login", json={"password": "not-the-password"})
    assert res.status_code == 401
    assert anon_client.get("/api/v1/admin/session").json()["authenticated"] is False


def test_login_with_correct_password_grants_access_to_gated_routes():
    with TestClient(app) as client:
        settings = get_settings()
        login = client.post("/api/v1/admin/login", json={"password": settings.admin_password})
        assert login.status_code == 200, login.text
        assert login.json()["authenticated"] is True

        session = client.get("/api/v1/admin/session")
        assert session.json()["authenticated"] is True

        overview = client.get("/api/v1/admin/overview")
        assert overview.status_code == 200, overview.text


def test_logout_revokes_access():
    with TestClient(app) as client:
        settings = get_settings()
        client.post("/api/v1/admin/login", json={"password": settings.admin_password})
        assert client.get("/api/v1/admin/overview").status_code == 200

        logout = client.post("/api/v1/admin/logout")
        assert logout.status_code == 200
        assert logout.json()["authenticated"] is False

        assert client.get("/api/v1/admin/session").json()["authenticated"] is False
        assert client.get("/api/v1/admin/overview").status_code == 401


def test_tampered_session_cookie_is_rejected():
    with TestClient(app) as client:
        client.cookies.set("buddy_admin_session", "not-a-real-token")
        res = client.get("/api/v1/admin/overview")
        assert res.status_code == 401


def test_session_endpoint_never_itself_requires_login(anon_client):
    """The one gated-router-adjacent endpoint that must always be
    reachable, unauthenticated, so the frontend can ask "am I logged
    in?" without a chicken-and-egg 401."""
    res = anon_client.get("/api/v1/admin/session")
    assert res.status_code == 200

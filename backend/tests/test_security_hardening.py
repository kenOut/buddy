"""P5 — Production Security Hardening.

Covers what's genuinely NEW in this phase — the pre-existing suite
already has extensive coverage of admin-session gating
(test_admin_auth.py), employee-session validity/expiry/tampering
(test_employee_invitations.py), invitation lifecycle/concurrency
(test_employee_invitations.py), and provisioning-credential
boundaries/cross-credential rejection (test_provisioning.py) — none of
that is repeated here.

What this file adds:
  1. The real session-based IDOR closure (core/employee_auth.py's
     get_optional_employee_session + assert_caller_is_employee, wired
     into mission_attempts.py/capabilities.py/quests.py): a session
     genuinely belonging to Employee B, used against a request that
     targets Employee A's data via a client-supplied employee_id, must
     now be rejected — this is the exact gap that existed before P5,
     since every one of these endpoints previously trusted whatever
     employee_id the client supplied with no session check at all.
  2. CORS origin allow/deny behavior.
  3. Error-response security (a genuine 500, not just a 4xx) reveals no
     exception text/secret.
  4. Environment-aware cookie `secure` flag (admin + invitation-exchange).
  5. `Settings.api_docs_enabled` / `trusted_host_list` / `cors_origin_list`
     policy — unit-level, since the live `app` singleton is already
     built for development by the time tests run.
  6. The request body-size limit, against the real live middleware.

Runs against its own isolated SQLite file, same convention as every
other test_*.py module.
"""

import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_security_hardening.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import types  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import Settings, get_settings  # noqa: E402
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


def _new_employee_with_session(client, org_id, department_id, full_name, email):
    """Provisions a real employee, issues + exchanges a real invitation,
    and provisions their mission assignments via bundle/me — everything
    a genuine (non-demo) employee session would have done, so the
    session this returns is indistinguishable from a real one for the
    purposes of these tests."""
    employee = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department_id,
            "full_name": full_name,
            "email": email,
        },
    ).json()
    invitation = client.post(f"/api/v1/invitations/employees/{employee['id']}/issue").json()

    session = TestClient(app)
    exchange = session.post("/api/v1/invitations/exchange", json={"token": invitation["token"]})
    assert exchange.status_code == 200, exchange.text

    session.get("/api/v1/onboarding/bundle/me")  # provisions mission assignments
    return employee, session


# =====================================================================
# IDOR — session-based cross-employee rejection (the P5 finding)
# =====================================================================


@pytest.fixture(scope="module")
def department_mission_id(client, department_id):
    # seed_data.py no longer seeds any demo Missions (see its own module
    # docstring) — this file's employee fixtures below need at least one
    # Mission to exist in the department BEFORE those employees'
    # onboarding sessions are created, since mission assignments are
    # only ever provisioned once, at an employee's first bundle fetch
    # (P2 — Provisioning Boundary).
    res = client.post(
        "/api/v1/missions",
        json={
            "department_id": department_id,
            "title": "Security Test Mission",
            "mission_type": "task",
            "workspace_type": "reflection",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


@pytest.fixture(scope="module")
def employee_a(client, org_id, department_id, department_mission_id):
    return _new_employee_with_session(
        client, org_id, department_id, "Security Test Employee A", "sec-test-a@kowri.test"
    )


@pytest.fixture(scope="module")
def employee_b(client, org_id, department_id, department_mission_id):
    return _new_employee_with_session(
        client, org_id, department_id, "Security Test Employee B", "sec-test-b@kowri.test"
    )


@pytest.fixture(scope="module")
def shared_mission_id(client, employee_a):
    employee, _session = employee_a
    missions = client.get(f"/api/v1/employees/{employee['id']}/missions").json()
    assert missions, "expected at least one department-provisioned mission assignment"
    return missions[0]["mission_id"]


@pytest.fixture(scope="module")
def employee_a_mission_attempt(employee_a, shared_mission_id):
    employee, session = employee_a
    res = session.post(
        "/api/v1/mission-attempts",
        json={"mission_id": shared_mission_id, "employee_id": employee["id"]},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_employee_b_session_cannot_read_employee_a_mission_scenario(
    employee_a, employee_b, shared_mission_id
):
    """Before P5: any caller who knew mission_id + employee A's id could
    read A's scenario, regardless of whose session (if any) was
    attached — because the endpoint never checked the session at all.
    Employee B's session is real and valid, just for the wrong person."""
    employee_a_id = employee_a[0]["id"]
    _employee_b, session_b = employee_b
    res = session_b.get(
        f"/api/v1/missions/{shared_mission_id}/scenario", params={"employee_id": employee_a_id}
    )
    assert res.status_code == 403


def test_employee_b_session_cannot_read_employee_a_mission_attempt(
    employee_a, employee_b, shared_mission_id, employee_a_mission_attempt
):
    employee_a_id = employee_a[0]["id"]
    _employee_b, session_b = employee_b
    res = session_b.get(
        "/api/v1/mission-attempts",
        params={"mission_id": shared_mission_id, "employee_id": employee_a_id},
    )
    assert res.status_code == 403


def test_employee_b_session_cannot_create_mission_attempt_as_employee_a(
    employee_a, employee_b, shared_mission_id
):
    employee_a_id = employee_a[0]["id"]
    _employee_b, session_b = employee_b
    res = session_b.post(
        "/api/v1/mission-attempts",
        json={"mission_id": shared_mission_id, "employee_id": employee_a_id},
    )
    assert res.status_code == 403


def test_employee_b_session_cannot_patch_employee_a_mission_attempt(
    employee_a, employee_b, employee_a_mission_attempt
):
    """The endpoint with the most severe pre-P5 gap: MissionAttemptUpdate
    has no employee_id field at all, so there was previously ZERO
    ownership check of any kind on this route — closed via the
    attempt's own already-loaded employee_id, checked against the
    caller's session."""
    _employee_b, session_b = employee_b
    res = session_b.patch(
        f"/api/v1/mission-attempts/{employee_a_mission_attempt['id']}",
        json={"evidence_viewed": ["hijacked"]},
    )
    assert res.status_code == 403


def test_employee_a_session_can_still_read_and_patch_their_own_attempt(
    employee_a, shared_mission_id, employee_a_mission_attempt
):
    """The regression check: the legitimate owner, using their own real
    session, is completely unaffected by any of the above."""
    employee, session = employee_a
    res = session.get(
        "/api/v1/mission-attempts",
        params={"mission_id": shared_mission_id, "employee_id": employee["id"]},
    )
    assert res.status_code == 200, res.text

    patch = session.patch(
        f"/api/v1/mission-attempts/{employee_a_mission_attempt['id']}",
        json={"evidence_viewed": ["log-1"]},
    )
    assert patch.status_code == 200, patch.text


def test_unauthenticated_caller_with_no_session_is_unaffected(
    employee_a, shared_mission_id, employee_a_mission_attempt
):
    """Deliberately preserved, disclosed residual: a caller with NO
    session at all (demo mode's own zero-auth design, unchanged since
    the project's inception) is not blocked by assert_caller_is_employee
    — only a *mismatched, present* session is. This is the documented
    trade-off, not an oversight: see employee_auth.
    get_optional_employee_session's own docstring."""
    employee_a_id = employee_a[0]["id"]
    anon = TestClient(app)
    res = anon.get(
        "/api/v1/mission-attempts",
        params={"mission_id": shared_mission_id, "employee_id": employee_a_id},
    )
    assert res.status_code == 200


@pytest.fixture(scope="module")
def employee_a_quest(client, employee_a):
    """A published quest assigned only to employee A — built through
    the same admin Quest Builder flow test_quest_workspace.py uses."""
    employee, _session = employee_a
    quest = client.post(
        "/api/v1/quests",
        json={
            "title": "Security hardening test quest",
            "description": "A quest used only to test the P5 IDOR closure.",
            "quest_type": "INVESTIGATE",
            "workspace_type": "INVESTIGATION",
        },
    ).json()
    quest_id = quest["id"]
    client.post(
        f"/api/v1/quests/{quest_id}/tasks",
        json={"title": "Required task", "task_type": "INVESTIGATE", "required": True, "sort_order": 0},
    )
    client.post(
        f"/api/v1/quests/{quest_id}/evidence",
        json={"title": "Evidence", "evidence_type": "TEXT", "content": {"note": "item"}, "sort_order": 0},
    )
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
        json={"assignment_type": "EMPLOYEE", "employee_id": employee["id"]},
    )
    client.post(f"/api/v1/quests/{quest_id}/publish")
    return quest_id


@pytest.fixture(scope="module")
def employee_a_quest_attempt(employee_a, employee_a_quest):
    employee, session = employee_a
    res = session.post(
        "/api/v1/quest-attempts", json={"quest_id": employee_a_quest, "employee_id": employee["id"]}
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_employee_b_session_cannot_create_quest_attempt_as_employee_a(
    employee_a, employee_b, employee_a_quest
):
    employee_a_id = employee_a[0]["id"]
    _employee_b, session_b = employee_b
    res = session_b.post(
        "/api/v1/quest-attempts", json={"quest_id": employee_a_quest, "employee_id": employee_a_id}
    )
    assert res.status_code == 403


def test_employee_b_session_cannot_read_employee_a_quest_attempt(
    employee_a, employee_b, employee_a_quest_attempt
):
    employee_a_id = employee_a[0]["id"]
    _employee_b, session_b = employee_b
    res = session_b.get(
        f"/api/v1/quest-attempts/{employee_a_quest_attempt['id']}", params={"employee_id": employee_a_id}
    )
    assert res.status_code == 403


def test_employee_b_session_cannot_patch_employee_a_quest_attempt(
    employee_a, employee_b, employee_a_quest_attempt
):
    employee_a_id = employee_a[0]["id"]
    _employee_b, session_b = employee_b
    res = session_b.patch(
        f"/api/v1/quest-attempts/{employee_a_quest_attempt['id']}",
        json={"employee_id": employee_a_id, "reasoning": "hijacked"},
    )
    assert res.status_code == 403


def test_employee_b_session_cannot_read_employee_a_capabilities(client, employee_a, employee_b):
    employee_a_id = employee_a[0]["id"]
    _employee_b, session_b = employee_b
    res = session_b.get(f"/api/v1/employees/{employee_a_id}/capabilities")
    assert res.status_code == 403


def test_employee_b_session_cannot_read_employee_a_development_journey(employee_a, employee_b):
    employee_a_id = employee_a[0]["id"]
    _employee_b, session_b = employee_b
    res = session_b.get(f"/api/v1/employees/{employee_a_id}/development-journey")
    assert res.status_code == 403


def test_employee_b_session_cannot_read_employee_a_workspace_access(employee_a, employee_b):
    employee_a_id = employee_a[0]["id"]
    _employee_b, session_b = employee_b
    res = session_b.get(f"/api/v1/employees/{employee_a_id}/workspace-access")
    assert res.status_code == 403


def test_employee_b_session_cannot_read_employee_a_readiness_summary(employee_a, employee_b):
    employee_a_id = employee_a[0]["id"]
    _employee_b, session_b = employee_b
    res = session_b.get(f"/api/v1/employees/{employee_a_id}/readiness-summary")
    assert res.status_code == 403


def test_employee_b_session_cannot_list_employee_a_quests(employee_a, employee_b):
    employee_a_id = employee_a[0]["id"]
    _employee_b, session_b = employee_b
    res = session_b.get(f"/api/v1/employees/{employee_a_id}/quests")
    assert res.status_code == 403


def test_unauthenticated_caller_can_still_read_development_journey(employee_a):
    """Regression: demo mode's zero-session read of this endpoint (also
    covered in test_admin_auth.py) is unaffected."""
    employee_a_id = employee_a[0]["id"]
    anon = TestClient(app)
    res = anon.get(f"/api/v1/employees/{employee_a_id}/development-journey")
    assert res.status_code == 200


# =====================================================================
# CORS
# =====================================================================


def test_cors_allows_configured_origin(client):
    res = client.get(
        "/api/v1/capabilities", headers={"Origin": "http://localhost:3000"}
    )
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_rejects_unconfigured_origin(client):
    res = client.get(
        "/api/v1/capabilities", headers={"Origin": "https://evil.example"}
    )
    assert "access-control-allow-origin" not in {k.lower() for k in res.headers.keys()}


# =====================================================================
# Error-response security
# =====================================================================


def test_unhandled_exception_does_not_leak_details(monkeypatch):
    """A genuine 500 (not a 4xx business-logic error) must return the
    bare default Starlette/FastAPI body with zero leakage of the
    exception's own message — verified here by making a real service
    function raise something with a fake-secret-shaped string in it, and
    confirming that string never reaches the HTTP response.
    `raise_server_exceptions=False` is required for the TestClient to
    behave like a real deployed server here (otherwise it re-raises into
    the test process instead of returning the 500 response body a real
    client would see)."""
    import app.services.capability_service as capability_service

    marker = "sk-fake-secret-DATABASE_URL=postgres://user:hunter2@host/db"

    async def _boom(db):
        raise RuntimeError(marker)

    monkeypatch.setattr(capability_service, "list_capabilities", _boom)

    with TestClient(app, raise_server_exceptions=False) as c:
        res = c.get("/api/v1/capabilities")
        assert res.status_code == 500
        assert marker not in res.text
        assert "RuntimeError" not in res.text
        assert "Traceback" not in res.text


# =====================================================================
# Cookie `secure` flag — environment-aware, not hardcoded
# =====================================================================


def test_admin_login_cookie_is_not_secure_in_development(client):
    """The live app is running with environment=development throughout
    this whole test process (see every other test file's own
    Settings())."""
    res = client.post("/api/v1/admin/login", json={"password": get_settings().admin_password})
    set_cookie = res.headers.get("set-cookie", "")
    assert "buddy_admin_session" in set_cookie
    assert "secure" not in set_cookie.lower()


def test_admin_login_cookie_is_secure_when_settings_report_production(monkeypatch):
    """Isolated unit check of the environment-aware branch itself,
    without flipping the process-wide cached get_settings() singleton
    (which every other test file in this suite also depends on staying
    at its development value) — monkeypatches only the name admin.py
    itself resolved at import time (`from app.core.config import
    get_settings`), so nothing outside this one test observes the
    change."""
    import app.api.v1.endpoints.admin as admin_module

    fake_settings = types.SimpleNamespace(environment="production", admin_session_ttl_seconds=3600)
    monkeypatch.setattr(admin_module, "get_settings", lambda: fake_settings)

    with TestClient(app) as c:
        res = c.post("/api/v1/admin/login", json={"password": get_settings().admin_password})
        assert res.status_code == 200, res.text
        set_cookie = res.headers.get("set-cookie", "")
        assert "secure" in set_cookie.lower()


def test_invitation_exchange_cookie_is_secure_when_settings_report_production(
    monkeypatch, client, org_id, department_id
):
    import app.api.v1.endpoints.invitations as invitations_module

    employee = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department_id,
            "full_name": "Cookie Flag Test Employee",
            "email": "cookie-flag-test@kowri.test",
        },
    ).json()
    invitation = client.post(f"/api/v1/invitations/employees/{employee['id']}/issue").json()

    fake_settings = types.SimpleNamespace(environment="production", employee_session_ttl_seconds=3600)
    monkeypatch.setattr(invitations_module, "get_settings", lambda: fake_settings)

    anon = TestClient(app)
    res = anon.post("/api/v1/invitations/exchange", json={"token": invitation["token"]})
    assert res.status_code == 200, res.text
    set_cookie = res.headers.get("set-cookie", "")
    assert "secure" in set_cookie.lower()


# =====================================================================
# Settings policy — unit-level (the live `app` singleton was already
# built for development before these tests run, so these check the
# underlying logic directly rather than the running app instance)
# =====================================================================


def test_api_docs_enabled_by_default_outside_production():
    assert Settings(environment="development").api_docs_enabled is True


def test_api_docs_disabled_by_default_in_production():
    settings = Settings(
        environment="production",
        provisioning_api_key="k",
        app_base_url="https://buddy.kowri.example",
        admin_password="p",
        admin_session_secret="s1",
        employee_session_secret="s2",
        invitation_token_secret="s3",
        cors_origins="https://buddy.kowri.example",
    )
    assert settings.api_docs_enabled is False


def test_api_docs_explicit_override_wins_in_production():
    settings = Settings(
        environment="production",
        enable_api_docs=True,
        provisioning_api_key="k",
        app_base_url="https://buddy.kowri.example",
        admin_password="p",
        admin_session_secret="s1",
        employee_session_secret="s2",
        invitation_token_secret="s3",
        cors_origins="https://buddy.kowri.example",
    )
    assert settings.api_docs_enabled is True


def test_trusted_host_list_defaults_to_permissive():
    """"*" (accept any Host) — TrustedHostMiddleware treats a literal
    "*" entry as "skip host checking entirely", matching this app's
    default of not enforcing an application-level allowlist unless one
    is explicitly configured (see Settings.trusted_hosts)."""
    assert Settings(environment="development").trusted_host_list == ["*"]


def test_trusted_host_list_parses_configured_hosts():
    settings = Settings(environment="development", trusted_hosts="buddy.kowri.example,api.kowri.example")
    assert settings.trusted_host_list == ["buddy.kowri.example", "api.kowri.example"]


def test_cors_origin_list_parses_multiple_origins():
    settings = Settings(environment="development", cors_origins="https://a.example,https://b.example")
    assert settings.cors_origin_list == ["https://a.example", "https://b.example"]


# =====================================================================
# Request body size limit
# =====================================================================


def test_oversized_request_body_rejected(client):
    oversized_padding = "x" * (get_settings().max_request_body_bytes + 1024)
    res = client.post("/api/v1/admin/login", json={"password": oversized_padding})
    assert res.status_code == 413


def test_normal_sized_request_body_unaffected(client):
    res = client.post("/api/v1/admin/login", json={"password": "not-the-real-password"})
    assert res.status_code == 401

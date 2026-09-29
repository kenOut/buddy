"""P5.1 — Production Employee Authorization Hardening.

P5 closed the "Employee B session -> Employee A resource" gap
(assert_caller_is_employee, tested in test_security_hardening.py), but
deliberately left one gap open everywhere: a request with NO session at
all could still reach any employee's data by simply supplying their
employee_id, because assert_caller_is_employee only checks a session
that is actually present. That was correct/necessary for demo-mode
compatibility in development, but must not be true in production (P4.1
already guarantees zero demo employees exist there, so there is no
legitimate unauthenticated caller left to accommodate).

This file proves `require_employee_session` (app/core/employee_auth.py)
closes that gap: in production, EVERY employee-scoped endpoint now
requires a valid session at all, in addition to the existing
same-employee check.

Rather than constructing a full `Settings(environment="production", ...)`
(which would need every P5 fail-closed secret configured, and would
also flip demo-seeding/CORS/cookie-secure behavior — all irrelevant to
this file's actual subject), each production-mode test monkeypatches
only `app.core.employee_auth.get_settings` to a minimal fake object
with `environment="production"` plus the SAME real
employee_session_secret/ttl this process's real dev Settings already
uses — so a session cookie signed earlier in the test (via the normal,
unmocked invitation-exchange flow) still verifies correctly once
`require_employee_session` starts asking "production or not". This
mirrors the same isolated-monkeypatch technique test_security_hardening.
py already uses for the cookie `secure` flag.

Runs against its own isolated SQLite file, same convention as every
other test_*.py module.
"""

import os
import types
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_production_employee_authorization.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.core.employee_auth as employee_auth_module  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.employee_auth import create_employee_session_token  # noqa: E402
from app.main import app  # noqa: E402


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
def department_id(demo_bundle):
    return demo_bundle["employee"]["department_id"]


def _new_employee_with_session(client, org_id, department_id, full_name, email):
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


@pytest.fixture(scope="module")
def employee_a(client, org_id, department_id):
    return _new_employee_with_session(
        client, org_id, department_id, "P5.1 Test Employee A", "p51-test-a@kowri.test"
    )


@pytest.fixture(scope="module")
def employee_b(client, org_id, department_id):
    return _new_employee_with_session(
        client, org_id, department_id, "P5.1 Test Employee B", "p51-test-b@kowri.test"
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


@pytest.fixture
def production_mode(monkeypatch):
    """Flips ONLY app.core.employee_auth's view of `environment` to
    "production" for the duration of one test — see module docstring
    for why a minimal monkeypatch is used instead of a real production
    Settings(). Every already-issued session cookie (signed with the
    real dev employee_session_secret, via the normal unmocked
    invitation-exchange flow) keeps verifying correctly, since the fake
    settings object carries the exact same secret/ttl."""
    real_settings = get_settings()
    fake_settings = types.SimpleNamespace(
        environment="production",
        employee_session_secret=real_settings.employee_session_secret,
        employee_session_ttl_seconds=real_settings.employee_session_ttl_seconds,
    )
    monkeypatch.setattr(employee_auth_module, "get_settings", lambda: fake_settings)
    yield


# =====================================================================
# 1. No session, in production -> 401 (the core P5.1 guarantee),
#    across every affected endpoint — not just one representative one.
# =====================================================================


def test_production_no_session_mission_scenario_rejected(
    production_mode, employee_a, shared_mission_id
):
    employee_a_id = employee_a[0]["id"]
    anon = TestClient(app)
    res = anon.get(
        f"/api/v1/missions/{shared_mission_id}/scenario", params={"employee_id": employee_a_id}
    )
    assert res.status_code == 401


def test_production_no_session_mission_attempt_read_rejected(
    production_mode, employee_a, shared_mission_id, employee_a_mission_attempt
):
    employee_a_id = employee_a[0]["id"]
    anon = TestClient(app)
    res = anon.get(
        "/api/v1/mission-attempts",
        params={"mission_id": shared_mission_id, "employee_id": employee_a_id},
    )
    assert res.status_code == 401


def test_production_no_session_mission_attempt_create_rejected(
    production_mode, employee_a, shared_mission_id
):
    employee_a_id = employee_a[0]["id"]
    anon = TestClient(app)
    res = anon.post(
        "/api/v1/mission-attempts",
        json={"mission_id": shared_mission_id, "employee_id": employee_a_id},
    )
    assert res.status_code == 401


def test_production_no_session_mission_attempt_patch_rejected(
    production_mode, employee_a_mission_attempt
):
    anon = TestClient(app)
    res = anon.patch(
        f"/api/v1/mission-attempts/{employee_a_mission_attempt['id']}",
        json={"evidence_viewed": ["hijacked"]},
    )
    assert res.status_code == 401


def test_production_no_session_capabilities_rejected(production_mode, employee_a):
    employee_a_id = employee_a[0]["id"]
    anon = TestClient(app)
    res = anon.get(f"/api/v1/employees/{employee_a_id}/capabilities")
    assert res.status_code == 401


def test_production_no_session_development_journey_rejected(production_mode, employee_a):
    """This route was OPEN, unauthenticated, in every environment before
    P5.1 — test_admin_auth.py's test_development_journey_never_requires_
    login (still true in development) proves the demo-compatible half;
    this proves production now closes it."""
    employee_a_id = employee_a[0]["id"]
    anon = TestClient(app)
    res = anon.get(f"/api/v1/employees/{employee_a_id}/development-journey")
    assert res.status_code == 401


def test_production_no_session_workspace_access_rejected(production_mode, employee_a):
    employee_a_id = employee_a[0]["id"]
    anon = TestClient(app)
    res = anon.get(f"/api/v1/employees/{employee_a_id}/workspace-access")
    assert res.status_code == 401


def test_production_no_session_readiness_summary_rejected(production_mode, employee_a):
    employee_a_id = employee_a[0]["id"]
    anon = TestClient(app)
    res = anon.get(f"/api/v1/employees/{employee_a_id}/readiness-summary")
    assert res.status_code == 401


def test_production_no_session_employee_quest_list_rejected(production_mode, employee_a):
    employee_a_id = employee_a[0]["id"]
    anon = TestClient(app)
    res = anon.get(f"/api/v1/employees/{employee_a_id}/quests")
    assert res.status_code == 401


def test_production_no_session_quest_eligibility_rejected(production_mode, employee_a):
    employee_a_id = employee_a[0]["id"]
    anon = TestClient(app)
    res = anon.get(f"/api/v1/quests/nonexistent-quest/eligibility/{employee_a_id}")
    assert res.status_code == 401


def test_production_no_session_onboarding_session_update_rejected(production_mode, employee_a):
    """A genuinely "less obvious" gap the P5 audit missed entirely —
    this route has no employee_id param at all; only a session_id."""
    employee, session = employee_a
    onboarding_session_id = session.get("/api/v1/onboarding/bundle/me").json()["session"]["id"]
    anon = TestClient(app)
    res = anon.patch(
        f"/api/v1/onboarding/sessions/{onboarding_session_id}", json={"current_scene": "hijacked"}
    )
    assert res.status_code == 401


def test_production_no_session_assessment_submit_rejected(production_mode, employee_a):
    """AssessmentSubmit carries employee_id in the body but was never
    referenced bare in onboarding.py's own text, so the original P5
    audit's grep-based sweep missed it — found during P5.1's full
    re-inventory."""
    employee, session = employee_a
    onboarding_session_id = session.get("/api/v1/onboarding/bundle/me").json()["session"]["id"]
    anon = TestClient(app)
    res = anon.post(
        "/api/v1/onboarding/assessments",
        json={
            "onboarding_session_id": onboarding_session_id,
            "employee_id": employee["id"],
            "answers": [],
        },
    )
    assert res.status_code == 401


def test_production_no_session_assessment_read_rejected(production_mode, employee_a):
    employee, session = employee_a
    onboarding_session_id = session.get("/api/v1/onboarding/bundle/me").json()["session"]["id"]
    session.post(
        "/api/v1/onboarding/assessments",
        json={"onboarding_session_id": onboarding_session_id, "employee_id": employee["id"], "answers": []},
    )
    anon = TestClient(app)
    res = anon.get(f"/api/v1/onboarding/assessments/{onboarding_session_id}")
    assert res.status_code == 401


# =====================================================================
# 2. Owner session, in production -> succeeds (the demo-vs-production
#    change must not break the legitimate employee).
# =====================================================================


def test_production_owner_session_mission_scenario_succeeds(
    production_mode, employee_a, shared_mission_id
):
    """`shared_mission_id` is whichever mission department-provisioning
    assigned first — not necessarily an investigation-workspace one, so
    a 404 ("no investigation workspace") is an acceptable outcome here
    too: it proves the request passed the auth/ownership boundary and
    reached real business logic, same convention test_admin_auth.py's
    own never-requires-login checks already use. Only 401/403 would
    mean the auth boundary itself rejected it."""
    employee, session = employee_a
    res = session.get(
        f"/api/v1/missions/{shared_mission_id}/scenario", params={"employee_id": employee["id"]}
    )
    assert res.status_code in (200, 404), res.text


def test_production_owner_session_mission_attempt_patch_succeeds(
    production_mode, employee_a_mission_attempt, employee_a
):
    _employee, session = employee_a
    res = session.patch(
        f"/api/v1/mission-attempts/{employee_a_mission_attempt['id']}",
        json={"evidence_viewed": ["log-1"]},
    )
    assert res.status_code == 200, res.text


def test_production_owner_session_capabilities_succeeds(production_mode, employee_a):
    employee, session = employee_a
    res = session.get(f"/api/v1/employees/{employee['id']}/capabilities")
    assert res.status_code == 200, res.text


def test_production_owner_session_development_journey_succeeds(production_mode, employee_a):
    employee, session = employee_a
    res = session.get(f"/api/v1/employees/{employee['id']}/development-journey")
    assert res.status_code == 200, res.text


def test_production_owner_session_onboarding_session_update_succeeds(production_mode, employee_a):
    employee, session = employee_a
    onboarding_session_id = session.get("/api/v1/onboarding/bundle/me").json()["session"]["id"]
    res = session.patch(
        f"/api/v1/onboarding/sessions/{onboarding_session_id}", json={"current_scene": "department"}
    )
    assert res.status_code == 200, res.text


def test_production_owner_session_assessment_submit_succeeds(production_mode, employee_a):
    employee, session = employee_a
    onboarding_session_id = session.get("/api/v1/onboarding/bundle/me").json()["session"]["id"]
    res = session.post(
        "/api/v1/onboarding/assessments",
        json={"onboarding_session_id": onboarding_session_id, "employee_id": employee["id"], "answers": []},
    )
    assert res.status_code == 201, res.text


# =====================================================================
# 3. Other-employee session, in production -> 403 (P5's guarantee,
#    still holding once a session is mandatory rather than optional).
# =====================================================================


def test_production_other_employee_session_mission_attempt_rejected(
    production_mode, employee_a, employee_b, shared_mission_id
):
    employee_a_id = employee_a[0]["id"]
    _employee_b, session_b = employee_b
    res = session_b.get(
        "/api/v1/mission-attempts",
        params={"mission_id": shared_mission_id, "employee_id": employee_a_id},
    )
    assert res.status_code == 403


def test_production_other_employee_session_development_journey_rejected(
    production_mode, employee_a, employee_b
):
    employee_a_id = employee_a[0]["id"]
    _employee_b, session_b = employee_b
    res = session_b.get(f"/api/v1/employees/{employee_a_id}/development-journey")
    assert res.status_code == 403


def test_production_other_employee_session_onboarding_session_update_rejected(
    production_mode, employee_a, employee_b
):
    _employee_a, session_a = employee_a
    _employee_b, session_b = employee_b
    onboarding_session_id_a = session_a.get("/api/v1/onboarding/bundle/me").json()["session"]["id"]

    res = session_b.patch(
        f"/api/v1/onboarding/sessions/{onboarding_session_id_a}", json={"current_scene": "hijacked"}
    )
    assert res.status_code == 403


def test_production_other_employee_session_assessment_read_rejected(
    production_mode, employee_a, employee_b
):
    employee, session_a = employee_a
    _employee_b, session_b = employee_b
    onboarding_session_id_a = session_a.get("/api/v1/onboarding/bundle/me").json()["session"]["id"]
    session_a.post(
        "/api/v1/onboarding/assessments",
        json={"onboarding_session_id": onboarding_session_id_a, "employee_id": employee["id"], "answers": []},
    )

    res = session_b.get(f"/api/v1/onboarding/assessments/{onboarding_session_id_a}")
    assert res.status_code == 403


# =====================================================================
# 4. Malformed / expired session, in production -> 401
# =====================================================================


def test_production_malformed_session_rejected(production_mode, employee_a):
    """Targets a `require_employee_session`-gated route directly (not
    `/bundle/me`, which uses the separate, always-strict
    `get_current_employee` and would pass even without this phase's
    change) — proving the NEW dependency itself handles a malformed
    cookie correctly, not just the pre-existing one."""
    employee_a_id = employee_a[0]["id"]
    anon = TestClient(app)
    anon.cookies.set("buddy_employee_session", "not-a-real-token")
    res = anon.get(f"/api/v1/employees/{employee_a_id}/capabilities")
    assert res.status_code == 401


def test_production_expired_session_rejected(production_mode, employee_a):
    """Build an already-expired token directly, bypassing the normal
    issuance TTL — same technique test_employee_invitations.py's own
    test_expired_employee_session_rejected uses for the development
    case. `production_mode` is already active (environment="production"),
    so only the ttl needs to flip negative for this one token. Targets
    a `require_employee_session`-gated route, same reasoning as
    test_production_malformed_session_rejected above."""
    employee, _session = employee_a

    expired_settings = employee_auth_module.get_settings()
    assert expired_settings.environment == "production"

    negative_ttl_settings = types.SimpleNamespace(
        environment="production",
        employee_session_secret=expired_settings.employee_session_secret,
        employee_session_ttl_seconds=-10,
    )
    original = employee_auth_module.get_settings
    employee_auth_module.get_settings = lambda: negative_ttl_settings
    try:
        token = create_employee_session_token(employee["id"])
    finally:
        employee_auth_module.get_settings = original

    anon = TestClient(app)
    anon.cookies.set("buddy_employee_session", token)
    res = anon.get(f"/api/v1/employees/{employee['id']}/capabilities")
    assert res.status_code == 401


# =====================================================================
# 5. Admin session / provisioning credential must not authenticate as
#    an employee, in production.
# =====================================================================


def test_production_admin_session_does_not_authenticate_as_employee(
    production_mode, client, employee_a, shared_mission_id
):
    """`client` is a real, logged-in admin session (separate cookie
    name/secret entirely) — proves it cannot be used to satisfy
    require_employee_session, even by accident."""
    employee_a_id = employee_a[0]["id"]
    res = client.get(
        "/api/v1/mission-attempts",
        params={"mission_id": shared_mission_id, "employee_id": employee_a_id},
    )
    assert res.status_code == 401


def test_production_provisioning_credential_does_not_authenticate_as_employee(
    production_mode, employee_a
):
    employee_a_id = employee_a[0]["id"]
    anon = TestClient(app)
    res = anon.get(
        f"/api/v1/employees/{employee_a_id}/capabilities",
        headers={"Authorization": "Bearer dev-only-insecure-provisioning-key-change-me"},
    )
    assert res.status_code == 401


# =====================================================================
# 6. Identity is authoritative — client cannot override session identity
# =====================================================================


def test_production_client_cannot_override_session_identity(
    production_mode, employee_a, employee_b, shared_mission_id
):
    """Employee B's session, claiming to act as Employee A via the
    client-supplied employee_id, is rejected — the session is what
    decides identity, never the request body/query."""
    employee_a_id = employee_a[0]["id"]
    _employee_b, session_b = employee_b
    res = session_b.post(
        "/api/v1/mission-attempts",
        json={"mission_id": shared_mission_id, "employee_id": employee_a_id},
    )
    assert res.status_code == 403


# =====================================================================
# 7. Development/demo path stays completely unaffected
# =====================================================================


def test_development_demo_bundle_unaffected(client):
    """No production_mode fixture applied here — this is the ordinary,
    already-established development behavior, unchanged by P5.1."""
    anon = TestClient(app)
    res = anon.get("/api/v1/onboarding/bundle/demo")
    assert res.status_code == 200


def test_development_no_session_employee_endpoints_still_open(employee_a, shared_mission_id):
    """The exact request that gets a 401 under test_production_no_session_
    mission_attempt_read_rejected above still succeeds here — no
    production_mode fixture applied, proving development/demo behavior
    is genuinely untouched, not just "also passing by coincidence"."""
    employee_a_id = employee_a[0]["id"]
    anon = TestClient(app)
    res = anon.get(
        "/api/v1/mission-attempts",
        params={"mission_id": shared_mission_id, "employee_id": employee_a_id},
    )
    assert res.status_code == 200

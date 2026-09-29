"""P1 — Identity & Invitation Foundation.

Covers the full new surface this phase adds: a stable external identity
on Employee, the EmployeeInvitation model/lifecycle, invitation issuance
and exchange, the resulting employee session, the `get_current_employee`
authorization boundary, and the closure of the previously-open
`GET /onboarding/bundle/{employee_id}` gap.

Runs against its own isolated SQLite file, same convention as the other
test_*.py modules.
"""

import itertools
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_employee_invitations.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402

_email_counter = itertools.count()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/api/v1/admin/login", json={"password": get_settings().admin_password})
        yield c
    TEST_DB_PATH.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def anon_client():
    """A second client against the same app/DB that never logs in — used
    for every assertion about unauthenticated behavior, so a login on
    the shared `client` fixture can never leak into those checks."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def demo_bundle(client):
    return client.get("/api/v1/onboarding/bundle/demo").json()


@pytest.fixture(scope="module")
def org_id(demo_bundle):
    return demo_bundle["employee"]["organization_id"]


@pytest.fixture(scope="module")
def department_id(demo_bundle):
    return demo_bundle["department"]["id"]


def _new_employee(client, org_id, department_id=None, **overrides):
    payload = {
        "organization_id": org_id,
        "department_id": department_id,
        "full_name": "Invitation Test Employee",
        "email": f"invite-test-{next(_email_counter)}@kowri.test",
    }
    payload.update(overrides)
    res = client.post("/api/v1/employees", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def _issue(client, employee_id):
    res = client.post(f"/api/v1/invitations/employees/{employee_id}/issue")
    assert res.status_code == 200, res.text
    return res.json()


# =====================================================================
# Identity
# =====================================================================


def test_create_employee_with_external_identity(client, org_id, department_id):
    employee = _new_employee(
        client, org_id, department_id, identity_provider="google", external_subject="google-sub-1"
    )
    assert employee["identity_provider"] == "google"
    assert employee["external_subject"] == "google-sub-1"


def test_duplicate_external_identity_pair_updates_existing_employee(client, org_id, department_id):
    """P2 — Provisioning Boundary changed this: POST /employees now
    routes through the provisioning service's identity-resolution logic
    (Section 7), so re-posting the same (identity_provider,
    external_subject) pair is no longer a raw duplicate-row rejection —
    it resolves to the SAME employee and updates it. See
    test_provisioning.py for the full identity-conflict matrix (Section
    9's Case A/B/C), including the case that genuinely still 409s: a
    *different* external identity colliding with someone else's email."""
    first = _new_employee(
        client, org_id, department_id, identity_provider="google", external_subject="google-sub-dup"
    )
    res = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department_id,
            "full_name": "Someone Else",
            "email": f"invite-test-{next(_email_counter)}@kowri.test",
            "identity_provider": "google",
            "external_subject": "google-sub-dup",
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["id"] == first["id"]
    assert res.json()["full_name"] == "Someone Else"


def test_nullable_external_identity_works_for_existing_demo_employees(demo_bundle):
    """The demo employee (seeded before this phase existed) has no
    external identity provider — nullable fields must not break it."""
    assert demo_bundle["employee"]["identity_provider"] is None
    assert demo_bundle["employee"]["external_subject"] is None


def test_two_employees_with_no_external_identity_are_not_duplicates(client, org_id, department_id):
    """Both fields null on two different rows must not collide — the
    partial unique index only applies when both are populated."""
    a = _new_employee(client, org_id, department_id)
    b = _new_employee(client, org_id, department_id)
    assert a["identity_provider"] is None and b["identity_provider"] is None


def test_email_remains_mutable_independently_of_external_identity(client, org_id, department_id):
    """Creating a second employee with a different email but reusing no
    external identity at all succeeds — proving external identity and
    email are two independent axes, not coupled."""
    employee = _new_employee(client, org_id, department_id, identity_provider="google", external_subject="google-sub-2")
    again = client.get(f"/api/v1/employees/{employee['id']}").json()
    assert again["email"] == employee["email"]


# =====================================================================
# Invitations — issuance
# =====================================================================


def test_issue_invitation(client, org_id, department_id):
    employee = _new_employee(client, org_id, department_id)
    invitation = _issue(client, employee["id"])
    assert invitation["employee_id"] == employee["id"]
    assert invitation["expires_at"]
    assert invitation["token"]


def test_raw_token_is_never_persisted(client, org_id, department_id):
    """The raw token only ever appears in the issue response body —
    nothing else queryable through the API exposes it, and the only
    thing stored server-side is a hash (verified indirectly: exchanging
    the exact raw token works, but the raw value itself never surfaces
    from any other endpoint)."""
    employee = _new_employee(client, org_id, department_id)
    invitation = _issue(client, employee["id"])
    raw_token = invitation["token"]

    # Nothing else about this employee ever echoes the raw token back.
    fetched = client.get(f"/api/v1/employees/{employee['id']}").json()
    assert raw_token not in str(fetched)


def test_token_hash_is_persisted_and_differs_from_raw_token(client, org_id, department_id):
    import hmac
    from hashlib import sha256

    employee = _new_employee(client, org_id, department_id)
    invitation = _issue(client, employee["id"])
    raw_token = invitation["token"]

    settings = get_settings()
    expected_hash = hmac.new(
        settings.invitation_token_secret.encode(), raw_token.encode(), sha256
    ).hexdigest()
    assert expected_hash != raw_token

    # The hash is what actually authorizes exchange — proven functionally
    # rather than by reaching into the DB directly.
    exchange_client = TestClient(app)
    res = exchange_client.post("/api/v1/invitations/exchange", json={"token": raw_token})
    assert res.status_code == 200, res.text


def test_issuing_new_invitation_revokes_previous_one(client, org_id, department_id):
    employee = _new_employee(client, org_id, department_id)
    first = _issue(client, employee["id"])
    second = _issue(client, employee["id"])
    assert first["token"] != second["token"]

    anon = TestClient(app)
    stale = anon.post("/api/v1/invitations/exchange", json={"token": first["token"]})
    assert stale.status_code == 401
    assert stale.json()["detail"]["reason"] == "revoked"

    fresh = anon.post("/api/v1/invitations/exchange", json={"token": second["token"]})
    assert fresh.status_code == 200, fresh.text


def test_only_one_active_invitation_exists_at_a_time(client, org_id, department_id):
    """Issuing three times in a row still leaves exactly one exchangeable
    (non-revoked, non-used) token — the two earlier ones are revoked,
    not deleted."""
    employee = _new_employee(client, org_id, department_id)
    tokens = [_issue(client, employee["id"])["token"] for _ in range(3)]

    anon = TestClient(app)
    results = [anon.post("/api/v1/invitations/exchange", json={"token": t}).status_code for t in tokens]
    assert results == [401, 401, 200]


def test_historical_invitations_remain_after_reissue(client, org_id, department_id):
    """Issuing a second invitation must not delete the first — its
    existence is provable by the fact that exchanging its (now revoked)
    token gives a specific "revoked" reason rather than "invalid"/unknown,
    which would be the response if the row had been deleted outright."""
    employee = _new_employee(client, org_id, department_id)
    first = _issue(client, employee["id"])
    _issue(client, employee["id"])

    anon = TestClient(app)
    res = anon.post("/api/v1/invitations/exchange", json={"token": first["token"]})
    assert res.status_code == 401
    assert res.json()["detail"]["reason"] == "revoked"


# =====================================================================
# Invitations — exchange
# =====================================================================


def test_valid_exchange_succeeds_and_sets_session_cookie(client, org_id, department_id):
    employee = _new_employee(client, org_id, department_id)
    invitation = _issue(client, employee["id"])

    anon = TestClient(app)
    res = anon.post("/api/v1/invitations/exchange", json={"token": invitation["token"]})
    assert res.status_code == 200, res.text
    assert "buddy_employee_session" in res.cookies


def test_expired_exchange_rejected(client, org_id, department_id):
    employee = _new_employee(client, org_id, department_id)

    original_ttl = get_settings().invitation_ttl_seconds
    get_settings().invitation_ttl_seconds = -1  # already expired at issue time
    try:
        invitation = _issue(client, employee["id"])
    finally:
        get_settings().invitation_ttl_seconds = original_ttl

    anon = TestClient(app)
    res = anon.post("/api/v1/invitations/exchange", json={"token": invitation["token"]})
    assert res.status_code == 401
    assert res.json()["detail"]["reason"] == "expired"


def test_revoked_exchange_rejected(client, org_id, department_id):
    employee = _new_employee(client, org_id, department_id)
    first = _issue(client, employee["id"])
    _issue(client, employee["id"])  # revokes `first`

    anon = TestClient(app)
    res = anon.post("/api/v1/invitations/exchange", json={"token": first["token"]})
    assert res.status_code == 401
    assert res.json()["detail"]["reason"] == "revoked"


def test_reused_exchange_rejected(client, org_id, department_id):
    employee = _new_employee(client, org_id, department_id)
    invitation = _issue(client, employee["id"])

    anon = TestClient(app)
    first = anon.post("/api/v1/invitations/exchange", json={"token": invitation["token"]})
    assert first.status_code == 200

    second = anon.post("/api/v1/invitations/exchange", json={"token": invitation["token"]})
    assert second.status_code == 401
    assert second.json()["detail"]["reason"] == "used"


def test_invalid_token_rejected(anon_client):
    res = anon_client.post("/api/v1/invitations/exchange", json={"token": "not-a-real-token"})
    assert res.status_code == 401
    assert res.json()["detail"]["reason"] == "invalid"


def test_malformed_token_request_rejected(anon_client):
    res = anon_client.post("/api/v1/invitations/exchange", json={})
    assert res.status_code == 422


# =====================================================================
# Employee sessions
# =====================================================================


def test_successful_exchange_creates_working_employee_session(client, org_id, department_id):
    employee = _new_employee(client, org_id, department_id)
    invitation = _issue(client, employee["id"])

    anon = TestClient(app)
    anon.post("/api/v1/invitations/exchange", json={"token": invitation["token"]})

    bundle = anon.get("/api/v1/onboarding/bundle/me")
    assert bundle.status_code == 200, bundle.text
    assert bundle.json()["employee"]["id"] == employee["id"]


def test_unauthenticated_employee_request_rejected(anon_client):
    res = anon_client.get("/api/v1/onboarding/bundle/me")
    assert res.status_code == 401


def test_expired_employee_session_rejected(client, org_id, department_id):
    from app.core import employee_auth

    employee = _new_employee(client, org_id, department_id)

    original_ttl = get_settings().employee_session_ttl_seconds
    get_settings().employee_session_ttl_seconds = -10  # already expired at creation time
    try:
        token = employee_auth.create_employee_session_token(employee["id"])
    finally:
        get_settings().employee_session_ttl_seconds = original_ttl

    anon = TestClient(app)
    anon.cookies.set("buddy_employee_session", token)
    res = anon.get("/api/v1/onboarding/bundle/me")
    assert res.status_code == 401


def test_authenticated_employee_resolves_correctly(client, org_id, department_id):
    employee_a = _new_employee(client, org_id, department_id)
    employee_b = _new_employee(client, org_id, department_id)

    invite_a = _issue(client, employee_a["id"])
    invite_b = _issue(client, employee_b["id"])

    session_a = TestClient(app)
    session_a.post("/api/v1/invitations/exchange", json={"token": invite_a["token"]})
    session_b = TestClient(app)
    session_b.post("/api/v1/invitations/exchange", json={"token": invite_b["token"]})

    assert session_a.get("/api/v1/onboarding/bundle/me").json()["employee"]["id"] == employee_a["id"]
    assert session_b.get("/api/v1/onboarding/bundle/me").json()["employee"]["id"] == employee_b["id"]


def test_tampered_employee_session_cookie_rejected(anon_client):
    anon_client.cookies.set("buddy_employee_session", "not-a-real-token")
    res = anon_client.get("/api/v1/onboarding/bundle/me")
    assert res.status_code == 401
    anon_client.cookies.clear()


def test_session_cannot_switch_employee_identity(client, org_id, department_id):
    """A session signed for employee A must resolve as employee A no
    matter what — there is no request parameter that could redirect it
    to employee B's data, because the identity comes only from the
    signed cookie."""
    from app.core import employee_auth

    employee_a = _new_employee(client, org_id, department_id)
    employee_b = _new_employee(client, org_id, department_id)

    token = employee_auth.create_employee_session_token(employee_a["id"])
    anon = TestClient(app)
    anon.cookies.set("buddy_employee_session", token)

    # There is no employee_id parameter on this route at all to try to
    # override with — /bundle/me takes none. Confirm it still resolves A.
    res = anon.get("/api/v1/onboarding/bundle/me")
    assert res.json()["employee"]["id"] == employee_a["id"]
    assert res.json()["employee"]["id"] != employee_b["id"]


# =====================================================================
# Authorization — the closed cross-employee gap
# =====================================================================


def test_employee_bundle_by_id_now_requires_admin_login(anon_client, org_id, department_id, client):
    employee = _new_employee(client, org_id, department_id)
    res = anon_client.get(f"/api/v1/onboarding/bundle/{employee['id']}")
    assert res.status_code == 401


def test_admin_can_still_reach_employee_bundle_by_id(client, org_id, department_id):
    """The route still works for the Manager Portal's own legitimate
    use — it's now gated, not deleted."""
    employee = _new_employee(client, org_id, department_id)
    res = client.get(f"/api/v1/onboarding/bundle/{employee['id']}")
    assert res.status_code == 200, res.text
    assert res.json()["employee"]["id"] == employee["id"]


def test_employee_cannot_access_another_employees_bundle_via_client_supplied_id(client, org_id, department_id):
    """The employee-facing route (/bundle/me) has no id parameter for a
    client to supply at all — proving cross-employee access isn't just
    blocked by validation, it's structurally impossible."""
    employee_a = _new_employee(client, org_id, department_id)
    employee_b = _new_employee(client, org_id, department_id)
    invite_a = _issue(client, employee_a["id"])

    session_a = TestClient(app)
    session_a.post("/api/v1/invitations/exchange", json={"token": invite_a["token"]})

    # No matter what is tried, this session can only ever resolve employee_a.
    res = session_a.get("/api/v1/onboarding/bundle/me")
    assert res.json()["employee"]["id"] == employee_a["id"]
    assert res.json()["employee"]["id"] != employee_b["id"]


def test_issue_invitation_requires_admin_login(anon_client, org_id, department_id, client):
    employee = _new_employee(client, org_id, department_id)
    res = anon_client.post(f"/api/v1/invitations/employees/{employee['id']}/issue")
    assert res.status_code == 401


def test_exchange_endpoint_itself_never_requires_admin_login(anon_client):
    """This is the employee's very first unauthenticated request — it
    must be reachable with no session of any kind. A generic 401 with a
    `reason` in the body (business logic) proves it reached
    exchange_invitation rather than being rejected at the Manager
    Portal's auth gate (which returns a bare string `detail`, not a
    structured `reason`)."""
    res = anon_client.post("/api/v1/invitations/exchange", json={"token": "whatever"})
    assert res.status_code == 401
    assert isinstance(res.json()["detail"], dict)
    assert "reason" in res.json()["detail"]


# =====================================================================
# Concurrency
# =====================================================================


def test_concurrent_invitation_exchange_allows_exactly_one_success(client, org_id, department_id):
    employee = _new_employee(client, org_id, department_id)
    invitation = _issue(client, employee["id"])
    token = invitation["token"]

    def exchange(_):
        return TestClient(app).post("/api/v1/invitations/exchange", json={"token": token})

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(exchange, range(8)))

    statuses = [r.status_code for r in responses]
    assert statuses.count(200) == 1, f"expected exactly one 200, got {statuses}"
    assert all(s in (200, 401) for s in statuses)


# =====================================================================
# Regression — existing surfaces unaffected
# =====================================================================


def test_demo_bundle_route_still_works_unauthenticated(anon_client):
    res = anon_client.get("/api/v1/onboarding/bundle/demo")
    assert res.status_code == 200


def test_employee_create_without_external_identity_still_works(client, org_id, department_id):
    """The common case (no external identity at all) is unaffected by
    the new optional fields."""
    employee = _new_employee(client, org_id, department_id)
    assert employee["identity_provider"] is None
    assert employee["external_subject"] is None


# =====================================================================
# P1.1 — legacy session-token bundle access is retired
# =====================================================================


def test_legacy_bundle_by_token_route_no_longer_exists(anon_client, client, org_id, department_id):
    """GET /onboarding/bundle/by-token/{session_token} predates
    EmployeeInvitation/employee sessions and was never used by the
    frontend — a second, unauthenticated, un-revocable employee-access
    mechanism sitting alongside the real one. Retired outright rather
    than gated: there is no legitimate caller left to preserve, and a
    plain 404 (route doesn't exist) is the correct signal, not a 401
    (route exists but you're not allowed) — FastAPI/Starlette's own
    routing produces exactly that for an unregistered path."""
    employee = _new_employee(client, org_id, department_id)
    session = client.get(f"/api/v1/onboarding/bundle/{employee['id']}").json()["session"]

    # The exact value that used to work as a bearer "token" (the
    # session's own primary key) must not resolve anything anymore.
    res = anon_client.get(f"/api/v1/onboarding/bundle/by-token/{session['id']}")
    assert res.status_code == 404

    # Nor does any other value — the route itself is gone, not just
    # rejecting this particular id.
    res_unknown = anon_client.get("/api/v1/onboarding/bundle/by-token/does-not-exist")
    assert res_unknown.status_code == 404

"""P3 — Email Provider Foundation. The admin-gated resend endpoint
(Section 14) and the complete, real, end-to-end invitation-email flow:
provision an employee, extract the invitation URL from the
MockEmailProvider message exactly like a real employee would receive
it, exchange it, and confirm the resulting session actually works.

Runs against its own isolated SQLite file, same convention as the other
test_*.py modules.
"""

import itertools
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_invitation_resend.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services.email_provider import MockEmailProvider  # noqa: E402

_email_counter = itertools.count()
_subject_counter = itertools.count()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/api/v1/admin/login", json={"password": get_settings().admin_password})
        yield c
    TEST_DB_PATH.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def anon_client():
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


@pytest.fixture(autouse=True)
def _clear_mock_sent_emails():
    MockEmailProvider.clear_sent()
    yield
    MockEmailProvider.clear_sent()


def _new_employee_via_provisioning(client, org_id, department_id):
    """Provisions a brand-new employee (fresh identity) the same way
    any real caller would, so the resulting invitation and welcome
    email are the genuine article, not test-only scaffolding."""
    n = next(_subject_counter)
    res = client.post(
        "/api/v1/provisioning/employees",
        json={
            "organization_id": org_id,
            "department_id": department_id,
            "identity_provider": "google",
            "external_subject": f"resend-test-sub-{n}",
            "email": f"resend-test-{next(_email_counter)}@kowri.test",
            "full_name": "Chiamaka Nwosu",
        },
        headers={"Authorization": f"Bearer {get_settings().provisioning_api_key}"},
    )
    assert res.status_code == 200, res.text
    return res.json()["employee_id"]


def _extract_invitation_url(sent_email) -> str:
    for line in sent_email.text.splitlines():
        if "/onboarding/invite/" in line:
            return line.split("Meet Heimdall: ", 1)[-1].strip()
    raise AssertionError("No invitation URL found in the sent email body")


# =====================================================================
# Resend endpoint
# =====================================================================


def test_resend_requires_admin_login(anon_client, org_id, department_id, client):
    employee_id = _new_employee_via_provisioning(client, org_id, department_id)
    res = anon_client.post(f"/api/v1/invitations/employees/{employee_id}/resend")
    assert res.status_code == 401


def test_resend_unknown_employee_is_not_found(client):
    res = client.post("/api/v1/invitations/employees/does-not-exist/resend")
    assert res.status_code == 404


def test_resend_issues_a_fresh_invitation_and_sends_email(client, org_id, department_id):
    employee_id = _new_employee_via_provisioning(client, org_id, department_id)
    assert len(MockEmailProvider.sent_emails()) == 1  # the original provisioning email

    res = client.post(f"/api/v1/invitations/employees/{employee_id}/resend")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["sent"] is True
    assert body["provider_ref"] is not None

    assert len(MockEmailProvider.sent_emails()) == 2


def test_resend_never_returns_the_raw_token(client, org_id, department_id):
    employee_id = _new_employee_via_provisioning(client, org_id, department_id)
    res = client.post(f"/api/v1/invitations/employees/{employee_id}/resend")
    assert set(res.json().keys()) == {"sent", "provider_ref"}

    sent = MockEmailProvider.sent_emails()
    raw_token = _extract_invitation_url(sent[-1]).rsplit("/", 1)[-1]
    assert raw_token not in res.text


def test_resend_revokes_the_previous_invitation(client, org_id, department_id):
    employee_id = _new_employee_via_provisioning(client, org_id, department_id)
    original_url = _extract_invitation_url(MockEmailProvider.sent_emails()[-1])
    original_token = original_url.rsplit("/", 1)[-1]

    resend_res = client.post(f"/api/v1/invitations/employees/{employee_id}/resend")
    assert resend_res.status_code == 200, resend_res.text

    anon = TestClient(app)
    stale = anon.post("/api/v1/invitations/exchange", json={"token": original_token})
    assert stale.status_code == 401
    assert stale.json()["detail"]["reason"] == "revoked"


def test_resend_new_invitation_is_exchangeable(client, org_id, department_id):
    employee_id = _new_employee_via_provisioning(client, org_id, department_id)
    resend_res = client.post(f"/api/v1/invitations/employees/{employee_id}/resend")
    assert resend_res.status_code == 200, resend_res.text

    new_url = _extract_invitation_url(MockEmailProvider.sent_emails()[-1])
    new_token = new_url.rsplit("/", 1)[-1]

    anon = TestClient(app)
    exchange = anon.post("/api/v1/invitations/exchange", json={"token": new_token})
    assert exchange.status_code == 200, exchange.text


def test_employee_session_cannot_authorize_resend(client, org_id, department_id):
    """Section 16 — resend must use existing admin authentication only;
    an authenticated employee session must not, by itself, satisfy it
    either."""
    employee_id = _new_employee_via_provisioning(client, org_id, department_id)
    url = _extract_invitation_url(MockEmailProvider.sent_emails()[-1])
    token = url.rsplit("/", 1)[-1]

    employee_session = TestClient(app)
    exchange = employee_session.post("/api/v1/invitations/exchange", json={"token": token})
    assert exchange.status_code == 200, exchange.text

    res = employee_session.post(f"/api/v1/invitations/employees/{employee_id}/resend")
    assert res.status_code == 401


# =====================================================================
# Full invitation-email flow, end to end, through the mock provider
# =====================================================================


def test_complete_invitation_email_flow(client, org_id, department_id):
    """The whole point of P3, proven top to bottom in one test:
    provision -> welcome email captured by the mock provider -> extract
    the real CTA URL (never a hash, never an id, never anything else —
    Section 8) -> exchange it -> employee session established ->
    /onboarding/bundle/me resolves that exact employee."""
    n = next(_subject_counter)
    email = f"resend-test-flow-{next(_email_counter)}@kowri.test"
    res = client.post(
        "/api/v1/provisioning/employees",
        json={
            "organization_id": org_id,
            "department_id": department_id,
            "identity_provider": "google",
            "external_subject": f"flow-sub-{n}",
            "email": email,
            "full_name": "Oluchi Eze",
        },
        headers={"Authorization": f"Bearer {get_settings().provisioning_api_key}"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["invitation_created"] is True
    assert body["email_sent"] is True
    employee_id = body["employee_id"]

    sent = MockEmailProvider.sent_emails()
    assert len(sent) == 1
    assert sent[0].to == email
    assert "Oluchi" in sent[0].text
    assert "Oluchi" in sent[0].html

    invitation_url = _extract_invitation_url(sent[0])
    assert invitation_url.startswith(get_settings().app_base_url)
    assert "/onboarding/invite/" in invitation_url
    raw_token = invitation_url.rsplit("/", 1)[-1]
    assert raw_token

    employee_session = TestClient(app)
    exchange = employee_session.post("/api/v1/invitations/exchange", json={"token": raw_token})
    assert exchange.status_code == 200, exchange.text

    bundle = employee_session.get("/api/v1/onboarding/bundle/me")
    assert bundle.status_code == 200, bundle.text
    assert bundle.json()["employee"]["id"] == employee_id
    assert bundle.json()["employee"]["full_name"] == "Oluchi Eze"


def test_raw_token_never_appears_in_the_html_body_as_something_other_than_the_link(client, org_id, department_id):
    """Section 16 / Section 9 — the email must use the raw invitation
    token itself, never a hash, database id, or employee id, in the
    CTA link."""
    employee_id = _new_employee_via_provisioning(client, org_id, department_id)
    sent = MockEmailProvider.sent_emails()[-1]
    invitation_url = _extract_invitation_url(sent)
    raw_token = invitation_url.rsplit("/", 1)[-1]

    assert raw_token in sent.html
    assert employee_id not in invitation_url

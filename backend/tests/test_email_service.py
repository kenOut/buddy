"""P3 — Email Provider Foundation. email_templates.py's rendering and
email_service.py's send/failure-handling behavior — both exercised
directly, with no database and no running application, same reasoning
as test_email_provider.py.

Settings (email_provider/app_base_url) are read via get_settings(),
which is @lru_cache'd process-wide — this file relies on the same
"development" defaults every other test in this suite already runs
under (see app/core/config.py), never overriding environment.
"""

import asyncio

import pytest

from app.services.email_provider import MockEmailProvider
from app.services.email_service import build_invitation_url, send_welcome_invitation_email
from app.services.email_templates import WELCOME_EMAIL_SUBJECT, render_welcome_invitation_email


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clear_mock_sent_emails():
    MockEmailProvider.clear_sent()
    yield
    MockEmailProvider.clear_sent()


# =====================================================================
# Template rendering
# =====================================================================


def test_welcome_email_contains_employee_first_name():
    rendered = render_welcome_invitation_email(
        employee_full_name="Amara Chukwu", invitation_url="https://example.test/onboarding/invite/tok123"
    )
    assert "Amara" in rendered.text
    assert "Amara" in rendered.html
    assert "Chukwu" not in rendered.text  # first name only, matching the app's existing greeting convention


def test_welcome_email_contains_correct_meet_heimdall_url():
    url = "https://example.test/onboarding/invite/a-real-raw-token"
    rendered = render_welcome_invitation_email(employee_full_name="Amara Chukwu", invitation_url=url)
    assert url in rendered.text
    assert url in rendered.html


def test_welcome_email_subject_matches_spec():
    rendered = render_welcome_invitation_email(employee_full_name="Amara", invitation_url="https://x.test/i/t")
    assert rendered.subject == "Welcome to Kowri Technologies — Meet Your Buddy!"
    assert rendered.subject == WELCOME_EMAIL_SUBJECT


def test_welcome_email_generates_plain_text_version():
    rendered = render_welcome_invitation_email(employee_full_name="Amara", invitation_url="https://x.test/i/t")
    assert rendered.text
    assert "<" not in rendered.text  # no stray HTML in the text body


def test_welcome_email_generates_html_version():
    rendered = render_welcome_invitation_email(employee_full_name="Amara", invitation_url="https://x.test/i/t")
    assert "<html>" in rendered.html
    assert "Meet Heimdall" in rendered.html


def test_welcome_email_escapes_employee_name_in_html():
    """Defense in depth: provisioning is service-credential/admin-only,
    not unauthenticated-user input, but a name containing HTML-special
    characters must still never break or inject into the rendered
    markup."""
    rendered = render_welcome_invitation_email(
        employee_full_name='<script>alert(1)</script> Smith', invitation_url="https://x.test/i/t"
    )
    assert "<script>" not in rendered.html


def test_welcome_email_mentions_heimdall_and_onboarding_guidance():
    rendered = render_welcome_invitation_email(employee_full_name="Amara", invitation_url="https://x.test/i/t")
    assert "Heimdall" in rendered.text
    assert "Kowri Technologies" in rendered.text


# =====================================================================
# build_invitation_url
# =====================================================================


def test_build_invitation_url_uses_configured_app_base_url_and_raw_token():
    url = build_invitation_url("a-raw-token-value")
    assert url.endswith("/onboarding/invite/a-raw-token-value")
    assert url.startswith("http://localhost:3000")  # this process's dev default


def test_build_invitation_url_never_exposes_a_hash_or_id_in_place_of_the_token():
    url = build_invitation_url("the-actual-raw-token")
    assert "the-actual-raw-token" in url


# =====================================================================
# Email service send behavior
# =====================================================================


def test_send_welcome_invitation_email_succeeds_via_mock():
    outcome = run(
        send_welcome_invitation_email(
            employee_id="emp-1",
            employee_email="amara@kowri.test",
            employee_full_name="Amara Chukwu",
            raw_token="raw-token-abc",
        )
    )
    assert outcome.sent is True
    assert outcome.provider_ref is not None
    assert outcome.error is None

    sent = MockEmailProvider.sent_emails()
    assert len(sent) == 1
    assert sent[0].to == "amara@kowri.test"
    assert "Amara" in sent[0].text
    assert "raw-token-abc" in sent[0].text


def test_send_welcome_invitation_email_metadata_never_contains_raw_token():
    run(
        send_welcome_invitation_email(
            employee_id="emp-1",
            employee_email="amara@kowri.test",
            employee_full_name="Amara Chukwu",
            raw_token="super-secret-raw-token",
        )
    )
    sent = MockEmailProvider.sent_emails()
    assert "super-secret-raw-token" not in str(sent[0].metadata)
    assert sent[0].metadata == {"email_type": "welcome_invitation", "employee_id": "emp-1"}


def test_send_welcome_invitation_email_surfaces_provider_failure():
    """Provider failure is a structured, non-raising outcome — proven
    by directly monkeypatching get_email_provider's resolution via the
    settings-driven factory is awkward here, so this exercises the same
    contract MockEmailProvider(simulate_failure=True) already proves at
    the provider layer (test_email_provider.py), confirming
    email_service surfaces it unchanged rather than swallowing or
    upgrading it to a fake success."""
    import app.services.email_service as email_service_module

    class _FailingMockEmailProvider(MockEmailProvider):
        def __init__(self):
            super().__init__(simulate_failure=True)

    # email_service.py does `from ... import get_email_provider`, binding
    # its own module-local name — patching that name (not
    # email_provider_module's) is what actually takes effect here.
    original = email_service_module.get_email_provider
    email_service_module.get_email_provider = lambda _name: _FailingMockEmailProvider()
    try:
        outcome = run(
            send_welcome_invitation_email(
                employee_id="emp-1",
                employee_email="amara@kowri.test",
                employee_full_name="Amara Chukwu",
                raw_token="raw-token-abc",
            )
        )
    finally:
        email_service_module.get_email_provider = original

    assert outcome.sent is False
    assert outcome.error is not None
    assert MockEmailProvider.sent_emails() == []


def test_send_welcome_invitation_email_never_logs_the_raw_token(caplog):
    """Section 16/22 — the raw token must never appear in logs. The
    email body legitimately contains it (that's the whole point of the
    email); the structured log line email_service emits alongside every
    send must not."""
    import logging

    with caplog.at_level(logging.DEBUG, logger="buddy.email"):
        run(
            send_welcome_invitation_email(
                employee_id="emp-1",
                employee_email="amara@kowri.test",
                employee_full_name="Amara Chukwu",
                raw_token="a-very-secret-raw-token-value",
            )
        )

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "a-very-secret-raw-token-value" not in log_text
    assert "email_type=welcome_invitation" in log_text
    assert "employee_id=emp-1" in log_text


def test_send_welcome_invitation_email_never_raises_for_unimplemented_provider():
    """email_service catches EmailProviderError itself (Section 12 —
    domain state and provider delivery are separate concerns) — a
    misconfigured/unimplemented provider selection must become a
    structured failed outcome, never an exception the caller
    (provisioning_service) has to handle."""
    import app.services.email_service as email_service_module
    from app.core.config import get_settings

    original_provider = get_settings().email_provider
    get_settings().email_provider = "sendgrid"  # unimplemented — see get_email_provider
    try:
        outcome = run(
            email_service_module.send_welcome_invitation_email(
                employee_id="emp-1",
                employee_email="amara@kowri.test",
                employee_full_name="Amara Chukwu",
                raw_token="raw-token-abc",
            )
        )
    finally:
        get_settings().email_provider = original_provider

    assert outcome.sent is False
    assert outcome.error is not None
    assert "sendgrid" in outcome.error.lower()

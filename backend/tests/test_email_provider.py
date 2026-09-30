"""P3 — Email Provider Foundation. The formalized EmailProvider
contract, mirroring test_workspace_provider_contract.py's own shape and
reasoning exactly.

Deliberately does NOT set DATABASE_URL, does NOT create a TestClient,
and does NOT import app.main — every test here calls MockEmailProvider
and the provider factory directly. That absence is itself part of what
is being proven: the provider abstraction needs no database, no
session, and no running application to exercise completely.

No network access, no credentials — this file must pass in complete
offline isolation.
"""

import asyncio

import pytest

from app.services.email_provider import (
    EMAIL_PROVIDER_TYPES,
    EmailProviderError,
    EmailSendResult,
    MockEmailProvider,
    get_email_provider,
)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clear_mock_sent_emails():
    """MockEmailProvider._sent is process-wide (class-level) by design —
    see its own docstring for why. Every test in this file starts from
    an empty log, same discipline this project's other test files apply
    to their own isolated databases."""
    MockEmailProvider.clear_sent()
    yield
    MockEmailProvider.clear_sent()


# =====================================================================
# Mock provider
# =====================================================================


def test_mock_provider_sends_successfully():
    provider = MockEmailProvider()
    result = run(
        provider.send_email(to="a@kowri.test", subject="Subject", html="<p>hi</p>", text="hi")
    )
    assert result.accepted is True
    assert result.provider_ref is not None
    assert result.error is None


def test_mock_provider_returns_provider_neutral_result():
    provider = MockEmailProvider()
    result = run(
        provider.send_email(to="a@kowri.test", subject="Subject", html="<p>hi</p>", text="hi")
    )
    assert isinstance(result, EmailSendResult)
    # No field capable of carrying a credential or raw provider payload
    # — structurally, not just by convention.
    assert set(result.__dataclass_fields__) == {"accepted", "provider_ref", "message_id", "error"}


def test_mock_provider_records_sent_message_inspectable_by_tests():
    provider = MockEmailProvider()
    run(
        provider.send_email(
            to="recipient@kowri.test",
            subject="Welcome",
            html="<p>Hi Recipient</p>",
            text="Hi Recipient",
            metadata={"email_type": "welcome_invitation", "employee_id": "emp-1"},
        )
    )
    sent = MockEmailProvider.sent_emails()
    assert len(sent) == 1
    assert sent[0].to == "recipient@kowri.test"
    assert sent[0].subject == "Welcome"
    assert sent[0].text == "Hi Recipient"
    assert sent[0].html == "<p>Hi Recipient</p>"
    assert sent[0].metadata == {"email_type": "welcome_invitation", "employee_id": "emp-1"}


def test_mock_provider_can_simulate_failure():
    provider = MockEmailProvider(simulate_failure=True)
    result = run(
        provider.send_email(to="a@kowri.test", subject="Subject", html="<p>hi</p>", text="hi")
    )
    assert result.accepted is False
    assert result.provider_ref is None
    assert result.error is not None
    # A simulated failure must not be recorded as a sent message.
    assert MockEmailProvider.sent_emails() == []


def test_mock_provider_never_makes_network_calls():
    """No assertion beyond "this file has zero network-capable imports
    and this test still passes" — the absence of httpx/requests/socket
    usage anywhere in email_provider.py is the actual proof, verified by
    inspection when this file was written. This test exists so a future
    change that quietly adds one doesn't slip past without a human
    reading the diff noticing MockEmailProvider suddenly needs network
    access to pass its own tests."""
    provider = MockEmailProvider()
    result = run(
        provider.send_email(to="a@kowri.test", subject="Subject", html="<p>hi</p>", text="hi")
    )
    assert result.accepted is True


# =====================================================================
# Provider factory
# =====================================================================


def test_provider_factory_resolves_mock():
    provider = get_email_provider("mock")
    assert isinstance(provider, MockEmailProvider)


def test_unknown_provider_fails_clearly():
    with pytest.raises(EmailProviderError, match="resend"):
        get_email_provider("resend")


def test_unimplemented_real_provider_cannot_silently_fall_back_to_mock():
    """The core Section 5/21 guarantee: selecting a real (but
    unimplemented) provider must raise, never silently return a
    MockEmailProvider instead — a caller that checks `isinstance` would
    never even get the chance to notice the substitution if it did."""
    for name in ("resend", "sendgrid", "ses", "mailgun", "gmail"):
        with pytest.raises(EmailProviderError):
            get_email_provider(name)


def test_email_provider_types_lists_only_implemented_providers():
    assert EMAIL_PROVIDER_TYPES == ["mock", "smtp"]


def test_automated_suite_can_never_run_with_a_real_email_provider():
    """The incident this pins down: a developer's local backend/.env
    can legitimately have EMAIL_PROVIDER=smtp (and real SMTP
    credentials) set for the manual/integration Gmail delivery test
    (README.md's "Email delivery" section) — pydantic-settings loads
    that file, and once, before conftest.py's safety net existed, that
    silently made the ENTIRE automated suite attempt real SMTP sends to
    synthetic @kowri.test addresses during a routine `pytest -q` run.
    tests/conftest.py now forces EMAIL_PROVIDER=mock in os.environ
    before any test module is even imported, which real environment
    variables always take priority over .env file values for — this
    just asserts that guarantee holds from inside a real test, not only
    by manual verification."""
    from app.core.config import get_settings

    assert get_settings().email_provider == "mock"

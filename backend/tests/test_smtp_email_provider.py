"""P3.1 — Real Gmail SMTP Welcome Email Delivery.

Covers SMTPEmailProvider and the new SMTP-selected fail-closed
validator (`Settings._require_smtp_config_when_selected`). Mirrors
test_email_provider.py's own offline-isolation discipline: `smtplib.SMTP`
is mocked in every test here — this file must never attempt a real
network connection or depend on Gmail being reachable. Real delivery is
a separate, manual/integration procedure (see README.md), never part of
the automated suite.

Deliberately does NOT set DATABASE_URL and does NOT import app.main —
SMTPEmailProvider, like MockEmailProvider, needs no database or running
application to exercise completely.
"""

import asyncio
import smtplib
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.services.email_provider import (
    EmailSendResult,
    MockEmailProvider,
    SMTPEmailProvider,
    _sanitize_smtp_error,
    get_email_provider,
)


def run(coro):
    return asyncio.run(coro)


def _provider(**overrides) -> SMTPEmailProvider:
    kwargs = dict(
        host="smtp.gmail.com",
        port=587,
        username="test@gmail.com",
        password="a-fake-app-password-value",
        from_email="test@gmail.com",
        from_name="Heimdall",
    )
    kwargs.update(overrides)
    return SMTPEmailProvider(**kwargs)


# =====================================================================
# 1. SMTP configuration validation
# =====================================================================


def test_selecting_smtp_without_config_fails_closed():
    with pytest.raises(ValueError, match="EMAIL_PROVIDER=smtp requires"):
        Settings(email_provider="smtp")


def test_selecting_smtp_without_config_names_every_missing_field():
    with pytest.raises(ValueError) as exc_info:
        Settings(email_provider="smtp")
    message = str(exc_info.value)
    for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_FROM"):
        assert name in message


def test_selecting_smtp_with_full_config_succeeds():
    settings = Settings(
        email_provider="smtp",
        smtp_host="smtp.gmail.com",
        smtp_username="test@gmail.com",
        smtp_password="a-fake-app-password-value",
        email_from="test@gmail.com",
    )
    assert settings.email_provider == "smtp"
    assert settings.smtp_port == 587  # default, STARTTLS


def test_mock_provider_never_requires_smtp_config():
    """The default, unchanged from P3 — constructing Settings() with no
    SMTP fields at all must not raise."""
    settings = Settings()
    assert settings.email_provider == "mock"


def test_smtp_config_error_never_contains_the_password_value():
    with pytest.raises(ValueError) as exc_info:
        Settings(
            email_provider="smtp",
            smtp_host="smtp.gmail.com",
            smtp_username="test@gmail.com",
            # smtp_password and email_from deliberately omitted
        )
    assert "a-fake-app-password-value" not in str(exc_info.value)


# =====================================================================
# 2. Implements the EmailProvider contract
# =====================================================================


def test_smtp_provider_send_email_returns_email_send_result():
    with patch("app.services.email_provider.smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server
        provider = _provider()
        result = run(provider.send_email(to="amara@kowri.test", subject="s", html="<p>h</p>", text="t"))
    assert isinstance(result, EmailSendResult)


def test_smtp_provider_accepts_the_same_kwargs_mock_provider_does():
    """Structural proof it satisfies the Protocol's signature — the
    Protocol itself is not @runtime_checkable (deliberately unmodified,
    Section 2's "do not modify the contract" instruction), so this
    calls it exactly the way email_service.py does rather than an
    isinstance check."""
    with patch("app.services.email_provider.smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server
        provider = _provider()
        result = run(
            provider.send_email(
                to="amara@kowri.test",
                subject="s",
                html="<p>h</p>",
                text="t",
                metadata={"email_type": "welcome_invitation", "employee_id": "emp-1"},
            )
        )
    assert result.accepted is True


# =====================================================================
# 3. Constructs a valid MIME email
# =====================================================================


def test_smtp_provider_builds_message_with_correct_headers():
    provider = _provider()
    msg = provider._build_message(
        to="amara@kowri.test", subject="Welcome to Kowri", html="<p>hi Amara</p>", text="hi Amara"
    )
    assert msg["To"] == "amara@kowri.test"
    assert msg["Subject"] == "Welcome to Kowri"
    assert msg["From"] == "Heimdall <test@gmail.com>"


def test_smtp_provider_builds_multipart_message_with_both_text_and_html():
    provider = _provider()
    msg = provider._build_message(to="amara@kowri.test", subject="s", html="<p>hi</p>", text="hi")
    content_types = [part.get_content_type() for part in msg.walk()]
    assert "text/plain" in content_types
    assert "text/html" in content_types


# =====================================================================
# 4. Calls STARTTLS and authenticates
# =====================================================================


def test_smtp_provider_calls_starttls_login_and_send():
    with patch("app.services.email_provider.smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server
        provider = _provider()
        result = run(provider.send_email(to="amara@kowri.test", subject="s", html="<p>h</p>", text="t"))

    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("test@gmail.com", "a-fake-app-password-value")
    mock_server.send_message.assert_called_once()
    assert result.accepted is True


# =====================================================================
# 5. Authentication failure is handled
# =====================================================================


def test_smtp_authentication_failure_returns_structured_failure_not_an_exception():
    with patch("app.services.email_provider.smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")
        mock_smtp_class.return_value.__enter__.return_value = mock_server
        provider = _provider()
        result = run(provider.send_email(to="amara@kowri.test", subject="s", html="<p>h</p>", text="t"))

    assert result.accepted is False
    assert "authentication" in result.error.lower()
    assert "a-fake-app-password-value" not in result.error


# =====================================================================
# 6. Send / connection failure is handled
# =====================================================================


def test_smtp_send_failure_returns_structured_failure():
    with patch("app.services.email_provider.smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_server.send_message.side_effect = smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
        mock_smtp_class.return_value.__enter__.return_value = mock_server
        provider = _provider()
        result = run(provider.send_email(to="amara@kowri.test", subject="s", html="<p>h</p>", text="t"))

    assert result.accepted is False
    assert result.error is not None


def test_smtp_connection_failure_returns_structured_failure():
    """DNS failure / connection refused / timeout — never reaches the
    SMTP protocol stage at all, so it's a plain OSError, not an
    smtplib.SMTPException subclass."""
    with patch("app.services.email_provider.smtplib.SMTP") as mock_smtp_class:
        mock_smtp_class.side_effect = OSError("Connection refused")
        provider = _provider()
        result = run(provider.send_email(to="amara@kowri.test", subject="s", html="<p>h</p>", text="t"))

    assert result.accepted is False
    assert result.error is not None


# =====================================================================
# 7. Success returns EmailSendResult (accepted=True + a provider_ref)
# =====================================================================


def test_smtp_success_returns_accepted_result_with_provider_ref():
    with patch("app.services.email_provider.smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server
        provider = _provider()
        result = run(provider.send_email(to="amara@kowri.test", subject="s", html="<p>h</p>", text="t"))

    assert result.accepted is True
    assert result.provider_ref is not None
    assert result.error is None


# =====================================================================
# 8. Credentials are never logged / never leak into an error message
# =====================================================================


def test_sanitize_smtp_error_never_includes_exception_text_verbatim():
    """_sanitize_smtp_error builds its string from the exception's TYPE
    and structured smtp_code only — never str(exc) — so even if a
    hypothetical future smtplib version put the password inside an
    exception's message text, it still could not reach the caller."""
    exc = smtplib.SMTPAuthenticationError(535, b"Authentication failed: a-fake-app-password-value")
    message = _sanitize_smtp_error(exc)
    assert "a-fake-app-password-value" not in message
    assert "535" in message


def test_smtp_provider_never_logs_credentials(caplog):
    import logging

    with caplog.at_level(logging.DEBUG):
        with patch("app.services.email_provider.smtplib.SMTP") as mock_smtp_class:
            mock_server = MagicMock()
            mock_smtp_class.return_value.__enter__.return_value = mock_server
            provider = _provider(password="a-fake-app-password-value")
            run(provider.send_email(to="amara@kowri.test", subject="s", html="<p>h</p>", text="t"))

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "a-fake-app-password-value" not in log_text


# =====================================================================
# 9. Raw invitation token is not persisted/logged via the SMTP path
# =====================================================================


def test_smtp_email_body_carries_the_token_but_metadata_and_provider_ref_never_do():
    """The token legitimately appears in the rendered email body (html/
    text) — that's the whole point of the email — but must never leak
    into provider_ref, message_id, or the metadata dict, exactly like
    the existing MockEmailProvider-based guarantee in test_email_service.
    py's test_send_welcome_invitation_email_metadata_never_contains_raw_
    token."""
    with patch("app.services.email_provider.smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server
        provider = _provider()
        result = run(
            provider.send_email(
                to="amara@kowri.test",
                subject="s",
                html="<p>Meet Heimdall: https://x.test/onboarding/invite/super-secret-raw-token</p>",
                text="Meet Heimdall: https://x.test/onboarding/invite/super-secret-raw-token",
                metadata={"email_type": "welcome_invitation", "employee_id": "emp-1"},
            )
        )

    assert "super-secret-raw-token" not in (result.provider_ref or "")
    assert "super-secret-raw-token" not in (result.message_id or "")


# =====================================================================
# 10. MockEmailProvider remains the default
# =====================================================================


def test_mock_remains_the_default_provider():
    settings = Settings()
    assert settings.email_provider == "mock"
    assert isinstance(get_email_provider(settings.email_provider), MockEmailProvider)


def test_smtp_is_never_selected_unless_explicitly_configured():
    """No implicit upgrade path — the only way EMAIL_PROVIDER becomes
    "smtp" is an operator setting it explicitly; nothing in this
    codebase ever does that automatically based on other configuration
    (e.g. environment=production does NOT imply smtp)."""
    settings = Settings(environment="production", **_PRODUCTION_SECRETS)
    assert settings.email_provider == "mock"


_PRODUCTION_SECRETS = dict(
    provisioning_api_key="k",
    app_base_url="https://buddy.kowri.example",
    admin_password="p",
    admin_session_secret="s1",
    employee_session_secret="s2",
    invitation_token_secret="s3",
    cors_origins="https://buddy.kowri.example",
)

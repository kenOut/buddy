"""Buddy's own email boundary — P3. The one place that decides WHAT to
send and calls the configured EmailProvider to send it, mirroring
workspace_access_service.py's boundary with WorkspaceProvider:

    ProvisioningService
            |
            v
      EmailService        <- this module
            |
            v
      EmailProvider (MockEmailProvider today; a real vendor eventually)

provisioning_service.py never imports email_provider directly, only
this module — exactly like it never imports SQLAlchemy models it
doesn't need. This module never imports SQLAlchemy models beyond the
plain strings it's handed, and never does anything provider-specific
(no branch shaped like `if settings.email_provider == "resend":`
anywhere in this file — that belongs entirely inside
email_provider.get_email_provider).

Failure handling mirrors _attempt_provider_grant's own principle
(workspace_access_service.py, Phase 8C): domain state and external
provider delivery are separate concerns. A provider failure here — or
an EmailProviderError from an unconfigured/unimplemented provider
selection — is caught and turned into a structured, non-raising
outcome; it never propagates into provisioning_service, and it never
rolls back or blocks the employee/session/invitation rows already
committed before this function was ever called.
"""

import logging
from dataclasses import dataclass

from app.core.config import get_settings
from app.services.email_provider import EmailProviderError, get_email_provider
from app.services.email_templates import render_welcome_invitation_email

logger = logging.getLogger("buddy.email")


@dataclass
class WelcomeEmailOutcome:
    """Provider-neutral result callers actually need — provisioning_service
    reads only this, never email_provider.EmailSendResult's own shape,
    so it doesn't need to import email_provider's types at all."""

    sent: bool
    provider_ref: str | None
    error: str | None


def build_invitation_url(raw_token: str) -> str:
    """The only place `{app_base_url}/onboarding/invite/{token}` is
    constructed — see config.py's app_base_url for why this can never
    silently be a localhost link in production."""
    settings = get_settings()
    base = settings.app_base_url.rstrip("/")
    return f"{base}/onboarding/invite/{raw_token}"


async def send_welcome_invitation_email(
    *,
    employee_id: str,
    employee_email: str,
    employee_full_name: str,
    raw_token: str,
) -> WelcomeEmailOutcome:
    """Sends the one email this project has (Section 7). `raw_token` is
    used only to build the CTA URL, passed straight through to the
    provider inside the rendered email body, and otherwise never
    touched, logged, stored, or echoed back by this function — the
    caller (provisioning_service, or the resend endpoint) already lets
    it go out of scope immediately after this call returns.

    Never raises: an EmailProviderError from an unconfigured/
    unimplemented provider selection is caught here, exactly like an
    ordinary provider-reported failure, and turned into the same
    WelcomeEmailOutcome(sent=False, ...) shape — the caller never needs
    a try/except around this call."""
    invitation_url = build_invitation_url(raw_token)
    rendered = render_welcome_invitation_email(
        employee_full_name=employee_full_name, invitation_url=invitation_url
    )

    settings = get_settings()
    try:
        provider = get_email_provider(settings.email_provider)
        result = await provider.send_email(
            to=employee_email,
            subject=rendered.subject,
            html=rendered.html,
            text=rendered.text,
            # Safe, non-secret tags only — never the raw token, never
            # anything from `rendered` itself. See email_provider.py's
            # own module docstring for this same boundary.
            metadata={"email_type": "welcome_invitation", "employee_id": employee_id},
        )
    except EmailProviderError as exc:
        logger.warning(
            "email_type=welcome_invitation employee_id=%s provider=%s accepted=false error=%s",
            employee_id,
            settings.email_provider,
            exc,
        )
        return WelcomeEmailOutcome(sent=False, provider_ref=None, error=str(exc))

    if result.accepted:
        logger.info(
            "email_type=welcome_invitation employee_id=%s provider=%s accepted=true",
            employee_id,
            settings.email_provider,
        )
    else:
        logger.warning(
            "email_type=welcome_invitation employee_id=%s provider=%s accepted=false error=%s",
            employee_id,
            settings.email_provider,
            result.error,
        )

    return WelcomeEmailOutcome(sent=result.accepted, provider_ref=result.provider_ref, error=result.error)

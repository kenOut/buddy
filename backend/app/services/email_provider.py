"""The email provider boundary — P3, mirroring
app/services/workspace_provider.py's shape deliberately: `EmailProvider`
is the interface every provider (mock or real) implements; the provider
returns a structured result and knows nothing about SQLAlchemy models,
onboarding sessions, or provisioning internals. Its responsibility is
delivery only — rendering the email is email_templates.py's job, and
deciding whether one should be sent at all is email_service.py's/
provisioning_service.py's.

No real provider is wired up here: no Resend/SendGrid/SES/Mailgun
credentials exist in this project, and none are invented.
`MockEmailProvider` is a deterministic stand-in — no randomness, no
network calls, no credentials — so local dev and tests exercise the
full welcome-email flow without any external dependency. Swapping in a
real provider later means implementing this same Protocol and adding a
branch to `get_email_provider` — nothing in email_service.py has to
change.

Contract every provider — Mock today, a real vendor eventually — must
satisfy identically:

  ACCEPTED: `EmailSendResult(accepted=True, provider_ref=<opaque
  external identifier>, message_id=<opaque, optional>, error=None)`.

  ORDINARY FAILURE (the external system ran and said no — e.g. a real
  provider's API rejects the request): `EmailSendResult(accepted=False,
  provider_ref=None, message_id=None, error=<short, operator-safe
  string>)`. Never a raised exception — this is a normal, expected
  outcome the caller must be able to handle without a try/except.

  PROVIDER UNAVAILABLE (no meaningful attempt could be made at all —
  unconfigured/unsupported provider selection, or, for a real provider,
  an auth client that can't be initialized): raise EmailProviderError.
  This is the only case a provider may raise for.

Security boundary: a provider receives to/subject/html/text/metadata —
plain strings and a plain string-to-string dict — and returns an opaque
provider_ref/message_id and a safe operator-facing error. A provider
must never return credentials, a raw upstream response body, or an
authorization header — EmailSendResult has no field capable of carrying
any of those, by construction. `metadata` is for safe, non-secret
tags only (see email_service.py's own usage — email_type/employee_id);
never the raw invitation token or anything else sensitive.
"""

from dataclasses import dataclass, field
from typing import ClassVar, Protocol
from uuid import uuid4

# Valid values for `settings.email_provider`. "mock" is the only
# implemented one in P3 — deliberately a short list, exactly like
# WORKSPACE_PROVIDER_TYPES was before a real provider existed for that
# boundary either.
EMAIL_PROVIDER_TYPES = ["mock"]


@dataclass
class EmailSendResult:
    """What a provider hands back to EmailService — never persisted
    verbatim, never a database write of its own. Structurally incapable
    of carrying a credential: it has no such field. See this module's
    docstring for the exact ACCEPTED/ORDINARY FAILURE field semantics
    every provider must follow identically."""

    accepted: bool
    provider_ref: str | None = None
    message_id: str | None = None
    error: str | None = None


class EmailProviderError(Exception):
    """Raised only when a provider cannot make a meaningful send attempt
    at all — never for an ordinary "the external system said no"
    outcome (that's an EmailSendResult with accepted=False). Examples:
    an unconfigured/unsupported provider selection (the only case
    reachable today, since no real provider is implemented); for a real
    provider, later: missing credentials, an auth client that can't be
    initialized, or total provider setup failure."""


class EmailProvider(Protocol):
    """An external-system adapter, nothing more: receives plain data,
    returns a plain result. Deliberately has no dependency on
    AsyncSession/SQLAlchemy or any domain model — proven by
    test_email_provider.py's DB-agnosticism (no database, no app
    import, at all)."""

    async def send_email(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: str,
        metadata: dict[str, str] | None = None,
    ) -> EmailSendResult:
        """Attempt to send one email. Returns an EmailSendResult
        regardless of ordinary outcome; may raise EmailProviderError if
        no attempt could be made at all. Never raises for an ordinary
        "the external system rejected this" outcome — that's
        accepted=False with `error` set."""
        ...


@dataclass
class SentEmail:
    """One recorded message — MockEmailProvider's own observability
    record, never a domain/persisted concept (see Section 20: P3
    deliberately adds no outbox/delivery-history table)."""

    to: str
    subject: str
    html: str
    text: str
    metadata: dict[str, str] = field(default_factory=dict)


class MockEmailProvider:
    """Deterministic, credential-free stand-in for a real provider —
    mirrors MockWorkspaceProvider's own design.

    Succeeds by default, recording the message and returning a stable
    (not random) provider reference derived from its inputs. Set
    `simulate_failure=True` at construction for a deterministic
    structured failure instead — a fixed, up-front configuration
    choice, not a reaction to which recipient/subject is passed in.

    Makes no network calls, requires no credentials, and writes nothing
    to the database — a pure recorder.

    `_sent` is intentionally a CLASS variable, not per-instance: callers
    (provisioning, the resend endpoint, tests, a browser-verification
    script hitting the real API) each construct a fresh provider via
    `get_email_provider("mock")` and have no other way to reach back
    into the specific instance used deep inside a request. Reading
    `MockEmailProvider.sent_emails()` at the class level is how a test
    or verification script inspects what was actually sent. Never used
    to make `send_email`'s own behavior depend on prior state — purely
    an observability log. Call `MockEmailProvider.clear_sent()` between
    tests that count exact messages sent, the same way each test file
    already resets its own database.
    """

    _sent: ClassVar[list[SentEmail]] = []

    def __init__(self, *, simulate_failure: bool = False) -> None:
        self.simulate_failure = simulate_failure

    async def send_email(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: str,
        metadata: dict[str, str] | None = None,
    ) -> EmailSendResult:
        if self.simulate_failure:
            return EmailSendResult(
                accepted=False,
                error="Mock provider configured to simulate a failure.",
            )

        sent = SentEmail(to=to, subject=subject, html=html, text=text, metadata=dict(metadata or {}))
        MockEmailProvider._sent.append(sent)
        return EmailSendResult(
            accepted=True,
            provider_ref=f"mock:{len(MockEmailProvider._sent)}:{to}",
            message_id=f"mock-{uuid4().hex}",
        )

    @classmethod
    def sent_emails(cls) -> list[SentEmail]:
        return list(cls._sent)

    @classmethod
    def clear_sent(cls) -> None:
        cls._sent.clear()


def get_email_provider(provider_name: str) -> EmailProvider:
    if provider_name == "mock":
        return MockEmailProvider()
    # No real provider is implemented in P3 (Section 5/21) — fail
    # loudly rather than silently falling back to MockEmailProvider,
    # exactly like get_workspace_provider's own google_drive branch.
    raise EmailProviderError(
        f"Unknown or unimplemented email provider: {provider_name!r}. "
        f"Supported values: {EMAIL_PROVIDER_TYPES}. Set EMAIL_PROVIDER=mock, "
        "or implement a real provider first."
    )

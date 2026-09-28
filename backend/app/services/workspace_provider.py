"""The workspace provider boundary — Phase 8C, contract formalized in
Phase 8F-1.

Mirrors app/services/ai_provider.py's shape deliberately: `WorkspaceProvider`
is the interface every provider (mock or real) implements; the provider
returns a structured result and never touches the database directly —
persistence and business state belong to WorkspaceAccessService, one
layer up, exactly like AIProvider's raw text is parsed and validated one
layer up in ai_evaluation_service.py, never inside a provider.

No real provider is wired up here: no Google credentials exist in this
project, and none are invented. `MockWorkspaceProvider` is a
deterministic stand-in — no randomness, no network calls, no database
writes — so local dev and tests exercise the full grant lifecycle
without any external dependency. Swapping in a real Google Drive
provider later means implementing this same Protocol and adding a
branch to `get_workspace_provider` — nothing in workspace_access_service.py
has to change.

Phase 8F-1 formalizes the contract every provider — Mock today,
GoogleDriveWorkspaceProvider eventually — must satisfy identically:

  SUCCESS: `WorkspaceGrantResult(success=True, provider_ref=<opaque
  external identifier>, workspace_link=<url or None>, error=None)`.
  Never a database write — WorkspaceAccessService owns persistence
  exclusively.

  ORDINARY FAILURE (the external system ran and said no — e.g. a real
  provider's permission-create call is rejected): `WorkspaceGrantResult
  (success=False, provider_ref=None or a safe diagnostic id,
  workspace_link=None or the existing configured link, error=<short,
  operator-safe string>)`. Never a raised exception — this is a normal,
  expected outcome the caller must be able to handle without a
  try/except.

  PROVIDER UNAVAILABLE (no meaningful attempt could be made at all —
  unconfigured/unsupported provider selection, or, for a real provider,
  an auth client that can't be initialized, fundamentally missing
  configuration, or total setup failure): raise WorkspaceProviderError.
  This is the only case a provider may raise for.

`provider_ref` is an opaque, provider-specific identifier (a Google
Drive permission ID, eventually) — the core application (WorkspaceAccess
Service and everything above it) must never parse, pattern-match, or
otherwise interpret its value. No code anywhere in this call chain may
contain logic shaped like `if provider_ref.startswith("google_"):` —
doing so would leak a provider-specific assumption into provider-
agnostic code, exactly what this boundary exists to prevent.

Security boundary: a provider may receive employee_email/workspace
external_ref/display_name/workspace_link, and may return an opaque
provider_ref, a safe workspace_link, and a short operator-safe error.
A provider must never return an access/refresh token, a private key,
service-account JSON, OAuth credentials, a raw upstream response body,
or an authorization header — WorkspaceGrantResult has no field capable
of carrying any of those, by construction.
"""

from dataclasses import dataclass
from typing import Protocol

from app.models import WorkspaceIntegration

# Valid values for `settings.workspace_provider` — which WorkspaceProvider
# *implementation* the app is configured to use. Deliberately a separate
# namespace from WorkspaceIntegration.WORKSPACE_PROVIDERS (models/
# workspace_integration.py), which lists what a department's stored
# `provider` column may legitimately be (real external systems only,
# currently just "google_drive"). "mock" is an application-level testing/
# dev toggle, never a value a real department's WorkspaceIntegration row
# would store.
WORKSPACE_PROVIDER_TYPES = ["mock", "google_drive"]


@dataclass
class WorkspaceGrantResult:
    """What a provider hands back to the service — never a mutated
    WorkspaceAccessGrant, so the provider layer can never accidentally
    (or intentionally) write business state itself. Structurally
    incapable of carrying a credential/token: it has no such field.

    See this module's docstring for the exact SUCCESS/ORDINARY FAILURE
    field semantics every provider must follow identically. `provider_ref`
    is opaque — callers must never interpret its value or shape."""

    success: bool
    provider_ref: str | None = None
    workspace_link: str | None = None
    error: str | None = None


class WorkspaceProviderError(Exception):
    """Raised only when a provider cannot make a meaningful grant attempt
    at all — never for an ordinary "the external system said no" outcome
    (that's a WorkspaceGrantResult with success=False). Examples: an
    unconfigured/unsupported provider selection (the only case reachable
    today); for a real provider, later: an authentication client that
    can't be initialized, fundamentally missing configuration, or total
    provider setup failure. The service treats both this exception and a
    structured success=False result the same way (grant -> FAILED), but
    only this exception path can occur before any real attempt happened
    at all — see workspace_access_service.py's PROVIDER_UNAVAILABLE
    handling."""


class WorkspaceProvider(Protocol):
    """An external-system adapter, nothing more: receives plain data,
    returns a plain result. Deliberately has no dependency on
    AsyncSession/SQLAlchemy or any domain model beyond the
    WorkspaceIntegration value it's handed — a provider implementation
    should be constructible and callable with zero database access,
    proven by test_workspace_provider_contract.py's DB-agnosticism
    tests. `workspace.external_ref` is opaque to this Protocol's callers
    too: the core application must never assume it is a Google-specific
    identifier, even though the eventual Google provider will interpret
    it as a Shared Drive ID — that interpretation belongs entirely
    inside the provider implementation."""

    async def grant_access(
        self, *, employee_email: str, workspace: WorkspaceIntegration
    ) -> WorkspaceGrantResult:
        """Attempt to grant `employee_email` access to `workspace`.
        Returns a WorkspaceGrantResult regardless of outcome where
        possible; may raise WorkspaceProviderError if no attempt could be
        made at all. Never raises for an ordinary "the external system
        rejected this" outcome — that's success=False with `error` set.

        Idempotency is this method's own responsibility, not the
        caller's: WorkspaceAccessService guarantees at most one
        WorkspaceAccessGrant row exists per (employee, workspace) and
        may call this method again for a PENDING/FAILED grant on a
        later retry, but does nothing to prevent that retry from
        reaching the external system a second time. A real
        implementation whose underlying operation isn't naturally
        idempotent (e.g. Google Drive's permission-creation) must make
        repeated calls for the same employee/workspace safe on its own
        — for the eventual GoogleDriveWorkspaceProvider, that means
        checking for an existing matching permission before creating a
        new one. MockWorkspaceProvider's operation has no side effects
        to duplicate, so it satisfies this trivially; that must not be
        mistaken for the caller providing this guarantee."""
        ...


class MockWorkspaceProvider:
    """Deterministic, credential-free stand-in for a real provider.

    Succeeds by default, returning a stable (not random) provider
    reference derived from its inputs and the workspace's own configured
    `workspace_link` — never invents a link the department didn't
    configure. Set `simulate_failure=True` at construction to get a
    deterministic structured failure instead, for testing the failure
    path — this is a fixed, up-front configuration choice, not a
    reaction to which employee/workspace is passed in: the mock never
    inspects employee/workspace values to decide whether to fail.

    Makes no network calls and writes nothing to the database — it is a
    pure function from (employee_email, workspace) to WorkspaceGrantResult.

    Deliberately provider-neutral in its own shape: no `google_permission_
    id`-style field, no Google-specific naming anywhere on this class.
    `provider_ref` values look like `"mock:<workspace_id>:<employee_email>"`
    — stable and inspectable for tests, not shaped to resemble any real
    provider's identifier format, so nothing accidentally couples to it.
    """

    def __init__(self, *, simulate_failure: bool = False) -> None:
        self.simulate_failure = simulate_failure

    async def grant_access(
        self, *, employee_email: str, workspace: WorkspaceIntegration
    ) -> WorkspaceGrantResult:
        if self.simulate_failure:
            return WorkspaceGrantResult(
                success=False,
                error="Mock provider configured to simulate a failure.",
            )

        return WorkspaceGrantResult(
            success=True,
            provider_ref=f"mock:{workspace.id}:{employee_email}",
            workspace_link=workspace.workspace_link,
        )


def get_workspace_provider(provider_name: str) -> WorkspaceProvider:
    if provider_name == "mock":
        return MockWorkspaceProvider()
    if provider_name == "google_drive":
        # Recognized as a real, eventual provider (see
        # models/workspace_integration.py's WORKSPACE_PROVIDERS) but not
        # implemented in Phase 8C — fail loudly rather than silently
        # pretending to work with no credentials configured.
        raise WorkspaceProviderError(
            "The google_drive workspace provider is not implemented yet. "
            "Set WORKSPACE_PROVIDER=mock, or implement a real "
            "GoogleDriveWorkspaceProvider first."
        )
    raise WorkspaceProviderError(
        f"Unknown workspace provider: {provider_name!r}. "
        f"Supported values: {WORKSPACE_PROVIDER_TYPES}."
    )

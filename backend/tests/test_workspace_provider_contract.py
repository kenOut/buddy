"""Phase 8F-1 backend tests: the formalized WorkspaceProvider contract.

Deliberately does NOT set DATABASE_URL, does NOT create a TestClient, and
does NOT import app.main — every test in this file calls
MockWorkspaceProvider and the provider factory directly, against a
plain, unpersisted WorkspaceIntegration object built in Python. That
absence is itself part of what's being proven: the provider contract
needs no database, no session, and no running application to exercise
completely (§7 — "the provider abstraction does not require AsyncSession/
SQLAlchemy session activity/WorkspaceAccessGrant/QuestAttempt/
ReadinessService/CapabilityProfile/Recommendation").

Covers: success/failure/provider-unavailable semantics exactly as
formalized in workspace_provider.py's module docstring, provider_ref
opacity, DB-agnosticism, contract neutrality (no Google-specific
assumptions anywhere in the core contract), and that repeated calls are
structurally permitted (idempotency is the provider's own job, not
tested here against real Google behavior — nothing Google-specific
exists yet).

No network access, no Google SDK, no credentials — this file must pass
in complete offline isolation.
"""

import asyncio
import inspect

import pytest

from app.models.workspace_integration import WorkspaceIntegration
from app.services.workspace_provider import (
    WORKSPACE_PROVIDER_TYPES,
    MockWorkspaceProvider,
    WorkspaceGrantResult,
    WorkspaceProviderError,
    get_workspace_provider,
)


def run(coro):
    return asyncio.run(coro)


def _make_workspace(**overrides) -> WorkspaceIntegration:
    """A plain, never-persisted WorkspaceIntegration — never added to a
    session, never committed. Constructing it this way is the point:
    proves a provider only ever needs the object's in-memory shape."""
    defaults = dict(
        id="fake-workspace-id",
        department_id="fake-department-id",
        provider="google_drive",
        external_ref="fake-shared-drive-id",
        display_name="Engineering Workspace",
        workspace_link="https://drive.google.com/drive/folders/fake",
        active=True,
    )
    defaults.update(overrides)
    return WorkspaceIntegration(**defaults)


# =====================================================================
# SUCCESS
# =====================================================================


def test_success_returns_success_true_with_provider_ref():
    provider = MockWorkspaceProvider()
    result = run(provider.grant_access(employee_email="a@kowri.test", workspace=_make_workspace()))
    assert result.success is True
    assert result.provider_ref is not None
    assert result.error is None


def test_success_workspace_link_matches_configured_link():
    workspace = _make_workspace(workspace_link="https://drive.google.com/drive/folders/unique-xyz")
    provider = MockWorkspaceProvider()
    result = run(provider.grant_access(employee_email="a@kowri.test", workspace=workspace))
    assert result.workspace_link == "https://drive.google.com/drive/folders/unique-xyz"


def test_success_result_is_a_plain_dataclass_not_a_db_row():
    provider = MockWorkspaceProvider()
    result = run(provider.grant_access(employee_email="a@kowri.test", workspace=_make_workspace()))
    assert isinstance(result, WorkspaceGrantResult)
    assert not hasattr(result, "id")
    assert not hasattr(result, "status")  # that's WorkspaceAccessGrant's field, not this result's


# =====================================================================
# ORDINARY FAILURE
# =====================================================================


def test_structured_failure_returns_success_false():
    provider = MockWorkspaceProvider(simulate_failure=True)
    result = run(provider.grant_access(employee_email="a@kowri.test", workspace=_make_workspace()))
    assert result.success is False
    assert result.error is not None


def test_structured_failure_never_raises():
    # No pytest.raises wrapper: if this call raised, the test itself
    # would fail with an unhandled exception — that failure mode IS the
    # property under test.
    provider = MockWorkspaceProvider(simulate_failure=True)
    result = run(provider.grant_access(employee_email="a@kowri.test", workspace=_make_workspace()))
    assert isinstance(result, WorkspaceGrantResult)


def test_failure_error_is_a_short_safe_string():
    provider = MockWorkspaceProvider(simulate_failure=True)
    result = run(provider.grant_access(employee_email="a@kowri.test", workspace=_make_workspace()))
    assert len(result.error) < 200
    assert "Traceback" not in result.error
    assert "\n" not in result.error


# =====================================================================
# PROVIDER UNAVAILABLE
# =====================================================================


def test_unconfigured_provider_selection_raises_workspace_provider_error():
    with pytest.raises(WorkspaceProviderError):
        get_workspace_provider("totally-unknown-provider")


def test_google_drive_not_implemented_raises_workspace_provider_error():
    with pytest.raises(WorkspaceProviderError):
        get_workspace_provider("google_drive")


def test_provider_unavailable_is_a_distinct_control_flow_from_structured_failure():
    """WorkspaceProviderError is a raised exception; a structured
    failure is a normal return value — these must never be conflated,
    proven here by their actual Python types, not by convention."""
    with pytest.raises(WorkspaceProviderError):
        get_workspace_provider("google_drive")

    result = run(
        MockWorkspaceProvider(simulate_failure=True).grant_access(
            employee_email="a@kowri.test", workspace=_make_workspace()
        )
    )
    assert not isinstance(result, BaseException)
    assert isinstance(result, WorkspaceGrantResult)


def test_provider_error_message_contains_no_credential_shaped_content():
    try:
        get_workspace_provider("google_drive")
        pytest.fail("expected WorkspaceProviderError")
    except WorkspaceProviderError as exc:
        text = str(exc).lower()
        for forbidden in ("token", "secret", "password", "private_key", "credential"):
            assert forbidden not in text


# =====================================================================
# CONTRACT NEUTRALITY — no Google-specific assumptions in the core contract
# =====================================================================


def test_mock_is_a_supported_provider_type():
    assert "mock" in WORKSPACE_PROVIDER_TYPES


def test_grant_result_has_no_google_shaped_field_names():
    forbidden = {"google_permission_id", "google_drive_id", "google_workspace_domain"}
    assert forbidden.isdisjoint(WorkspaceGrantResult.__dataclass_fields__.keys())


def test_mock_provider_instance_has_no_google_shaped_attributes():
    provider = MockWorkspaceProvider()
    forbidden = {"google_permission_id", "google_drive_id", "credentials", "service_account"}
    assert forbidden.isdisjoint(vars(provider).keys())


def test_google_sdk_is_not_an_installed_dependency():
    """Confirms the hard constraint held: no Google SDK was installed
    for this stage. If this ever starts passing an import, Phase 8F-1's
    "no Google dependencies" boundary has been violated."""
    with pytest.raises(ImportError):
        import googleapiclient  # noqa: F401


def test_workspace_provider_module_has_no_db_or_domain_imports():
    """§7 — proves the provider boundary is DB-agnostic by construction:
    it doesn't even import the names it would need to touch a database
    or reach into the Quest/capability domain."""
    import app.services.workspace_provider as mod

    forbidden_names = {
        "AsyncSession",
        "AsyncSessionLocal",
        "WorkspaceAccessGrant",
        "QuestAttempt",
        "CapabilityProfile",
        "Recommendation",
        "select",
        "IntegrityError",
        "readiness_service",
        "quest_evaluation_service",
    }
    assert forbidden_names.isdisjoint(vars(mod).keys())


def test_provider_callable_with_zero_database_setup():
    """The whole-file absence of DATABASE_URL/TestClient/app.main is the
    primary proof; this test additionally exercises the call path end
    to end to confirm it actually runs, not just that it could."""
    workspace = _make_workspace()
    provider = MockWorkspaceProvider()
    result = run(provider.grant_access(employee_email="a@kowri.test", workspace=workspace))
    assert result.success is True


def test_workspace_access_service_never_interprets_provider_ref():
    """§3 — the core application must never branch on provider_ref's
    shape (e.g. `if provider_ref.startswith("google_"):`). Checked
    directly against the source of the one module that ever writes
    provider_ref onto a grant."""
    import app.services.workspace_access_service as mod

    source = inspect.getsource(mod)
    assert "provider_ref.startswith" not in source
    assert "provider_ref.split" not in source
    assert "provider_ref[" not in source


# =====================================================================
# IDEMPOTENCY — interface permits repeated calls; provider owns safety
# =====================================================================


def test_repeated_grant_access_calls_are_permitted_by_the_interface():
    """Not testing Google's eventual list-before-create strategy (§8 of
    the architecture inspection) — that doesn't exist yet and isn't
    built here. This only proves the Protocol/Mock don't structurally
    reject being called twice for the same inputs; making repeated
    calls externally safe is the provider's own documented
    responsibility (see WorkspaceProvider.grant_access's docstring),
    not something WorkspaceAccessService or this test enforces."""
    workspace = _make_workspace()
    provider = MockWorkspaceProvider()

    result_a = run(provider.grant_access(employee_email="a@kowri.test", workspace=workspace))
    result_b = run(provider.grant_access(employee_email="a@kowri.test", workspace=workspace))

    assert result_a.success is True
    assert result_b.success is True
    assert result_a.provider_ref == result_b.provider_ref  # deterministic, not incidentally duplicated


# =====================================================================
# SECURITY CONTRACT
# =====================================================================


def test_grant_result_has_no_credential_shaped_fields():
    forbidden = {
        "credentials",
        "tokens",
        "access_token",
        "refresh_token",
        "client_secret",
        "private_key",
        "auth_header",
        "authorization",
    }
    assert forbidden.isdisjoint(WorkspaceGrantResult.__dataclass_fields__.keys())


def test_grant_access_signature_accepts_only_documented_safe_inputs():
    """§10 — a provider may receive employee_email and the workspace
    object (whose safe fields are external_ref/display_name/
    workspace_link/active); nothing resembling a credential is part of
    the call signature."""
    sig = inspect.signature(MockWorkspaceProvider.grant_access)
    param_names = set(sig.parameters.keys()) - {"self"}
    assert param_names == {"employee_email", "workspace"}

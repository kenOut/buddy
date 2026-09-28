"""Phase 8C backend tests: the workspace provider abstraction
(WorkspaceProvider protocol, MockWorkspaceProvider, get_workspace_provider
factory) and WorkspaceAccessService's grant lifecycle/idempotency/
failure-isolation behavior.

No ReadinessService, no trigger wired into evaluate_attempt(), no Google
provider, no API endpoints, no frontend — see the module docstrings in
app/services/workspace_provider.py and workspace_access_service.py for
what this stage is and isn't. Every call in this file goes directly
through the service functions, exactly like test_workspace_access_
foundation.py (Phase 8B) exercised the models directly — there is
nothing else to call yet.

Runs against its own isolated SQLite file, same convention as the other
test_*.py modules.
"""

import asyncio
import itertools
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_workspace_access_service.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

import app.services.workspace_access_service as was_mod  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Recommendation, WorkspaceAccessGrant, WorkspaceIntegration  # noqa: E402
from app.services.workspace_access_service import (  # noqa: E402
    EmployeeNotFoundError,
    WorkspaceIntegrationNotFoundError,
    ensure_access,
)
from app.services.workspace_provider import (  # noqa: E402
    MockWorkspaceProvider,
    WorkspaceProviderError,
    get_workspace_provider,
)

_email_counter = itertools.count()
_dept_counter = itertools.count()


def run(coro):
    return asyncio.run(coro)


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


@pytest.fixture
def department(client, org_id):
    return client.post(
        "/api/v1/departments",
        json={"organization_id": org_id, "name": f"WS Service Dept {next(_dept_counter)}"},
    ).json()


@pytest.fixture
def employee(client, org_id, department):
    return client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "full_name": "Workspace Service Employee",
            "email": f"workspace-service-{next(_email_counter)}@kowri.test",
        },
    ).json()


async def _create_integration(department_id: str, **overrides) -> WorkspaceIntegration:
    defaults = dict(
        department_id=department_id,
        provider="google_drive",
        external_ref="drive-folder-abc123",
        display_name="Engineering Workspace",
        workspace_link="https://drive.google.com/drive/folders/abc123",
    )
    defaults.update(overrides)
    async with AsyncSessionLocal() as db:
        integration = WorkspaceIntegration(**defaults)
        db.add(integration)
        await db.commit()
        await db.refresh(integration)
        return integration


@pytest.fixture
def workspace(department):
    return run(_create_integration(department["id"]))


async def _ensure_access(employee_id: str, workspace_integration_id: str) -> WorkspaceAccessGrant:
    async with AsyncSessionLocal() as db:
        return await ensure_access(db, employee_id, workspace_integration_id)


async def _get_grant_row(employee_id: str, workspace_integration_id: str) -> WorkspaceAccessGrant | None:
    async with AsyncSessionLocal() as db:
        stmt = select(WorkspaceAccessGrant).where(
            WorkspaceAccessGrant.employee_id == employee_id,
            WorkspaceAccessGrant.workspace_integration_id == workspace_integration_id,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


async def _count_grants(employee_id: str, workspace_integration_id: str) -> int:
    async with AsyncSessionLocal() as db:
        stmt = select(func.count()).select_from(WorkspaceAccessGrant).where(
            WorkspaceAccessGrant.employee_id == employee_id,
            WorkspaceAccessGrant.workspace_integration_id == workspace_integration_id,
        )
        result = await db.execute(stmt)
        return result.scalar_one()


class _CountingMockProvider(MockWorkspaceProvider):
    """A MockWorkspaceProvider that records how many times it was
    actually invoked — used to assert the service never calls the
    provider more than once per warranted attempt."""

    def __init__(self, *, simulate_failure: bool = False) -> None:
        super().__init__(simulate_failure=simulate_failure)
        self.call_count = 0

    async def grant_access(self, *, employee_email, workspace):
        self.call_count += 1
        return await super().grant_access(employee_email=employee_email, workspace=workspace)


class _RaisingProvider:
    """Simulates total provider unavailability — raises before ever
    producing a WorkspaceGrantResult, exercising the exception-handling
    path distinct from a structured success=False result."""

    async def grant_access(self, *, employee_email, workspace):
        raise WorkspaceProviderError("simulated total outage")


def _patch_provider(provider_factory):
    """Monkeypatches the module-level get_workspace_provider reference
    inside workspace_access_service, exactly the pattern already
    established for AIProvider in test_quest_evaluation.py
    (test_ai_failure_leaves_attempt_submitted_and_preserves_work)."""
    was_mod.get_workspace_provider = provider_factory


def _restore_provider():
    was_mod.get_workspace_provider = get_workspace_provider


# =====================================================================
# Provider
# =====================================================================


def test_mock_provider_succeeds(department):
    integration = run(_create_integration(department["id"]))
    provider = MockWorkspaceProvider()
    result = run(provider.grant_access(employee_email="a@kowri.test", workspace=integration))
    assert result.success is True


def test_mock_provider_returns_stable_provider_reference(department):
    integration = run(_create_integration(department["id"]))
    provider = MockWorkspaceProvider()
    result_a = run(provider.grant_access(employee_email="a@kowri.test", workspace=integration))
    result_b = run(provider.grant_access(employee_email="a@kowri.test", workspace=integration))
    assert result_a.provider_ref == result_b.provider_ref
    assert result_a.provider_ref is not None


def test_mock_provider_returns_configured_workspace_link(department):
    integration = run(
        _create_integration(department["id"], workspace_link="https://drive.google.com/drive/folders/unique-xyz")
    )
    provider = MockWorkspaceProvider()
    result = run(provider.grant_access(employee_email="a@kowri.test", workspace=integration))
    assert result.workspace_link == "https://drive.google.com/drive/folders/unique-xyz"


def test_mock_provider_deterministic_failure_mode(department):
    integration = run(_create_integration(department["id"]))
    provider = MockWorkspaceProvider(simulate_failure=True)
    result_a = run(provider.grant_access(employee_email="a@kowri.test", workspace=integration))
    result_b = run(provider.grant_access(employee_email="a@kowri.test", workspace=integration))
    assert result_a.success is False
    assert result_b.success is False
    assert result_a.error is not None


def test_unsupported_provider_configuration_fails_safely():
    with pytest.raises(WorkspaceProviderError):
        get_workspace_provider("google_drive")
    with pytest.raises(WorkspaceProviderError):
        get_workspace_provider("totally-unknown-provider")


# =====================================================================
# New grant — success path
# =====================================================================


def test_no_existing_grant_resolves_to_granted(employee, workspace):
    grant = run(_ensure_access(employee["id"], workspace.id))
    assert grant.status == "GRANTED"


def test_first_attempt_count_is_one(employee, workspace):
    grant = run(_ensure_access(employee["id"], workspace.id))
    assert grant.attempt_count == 1


def test_provider_reference_persisted(employee, workspace):
    grant = run(_ensure_access(employee["id"], workspace.id))
    assert grant.provider_ref is not None
    assert employee["email"] in grant.provider_ref


def test_granted_timestamp_persisted(employee, workspace):
    grant = run(_ensure_access(employee["id"], workspace.id))
    assert grant.granted_at is not None


# =====================================================================
# New grant — failure path
# =====================================================================


def test_no_existing_grant_resolves_to_failed(employee, workspace):
    _patch_provider(lambda name: MockWorkspaceProvider(simulate_failure=True))
    try:
        grant = run(_ensure_access(employee["id"], workspace.id))
    finally:
        _restore_provider()
    assert grant.status == "FAILED"


def test_failure_error_persisted(employee, workspace):
    _patch_provider(lambda name: MockWorkspaceProvider(simulate_failure=True))
    try:
        grant = run(_ensure_access(employee["id"], workspace.id))
    finally:
        _restore_provider()
    assert grant.last_error is not None


def test_failure_attempt_count_is_one(employee, workspace):
    _patch_provider(lambda name: MockWorkspaceProvider(simulate_failure=True))
    try:
        grant = run(_ensure_access(employee["id"], workspace.id))
    finally:
        _restore_provider()
    assert grant.attempt_count == 1


def test_raising_provider_does_not_escape_as_unhandled_exception(employee, workspace):
    """A provider that raises WorkspaceProviderError outright (total
    unavailability, not a structured failure) must still resolve to a
    FAILED grant — the exception must never propagate out of
    ensure_access."""
    _patch_provider(lambda name: _RaisingProvider())
    try:
        grant = run(_ensure_access(employee["id"], workspace.id))
    finally:
        _restore_provider()
    assert grant.status == "FAILED"
    assert "simulated total outage" in grant.last_error


# =====================================================================
# Idempotency
# =====================================================================


def test_granted_second_call_does_not_call_provider(employee, workspace):
    counting = _CountingMockProvider()
    _patch_provider(lambda name: counting)
    try:
        first = run(_ensure_access(employee["id"], workspace.id))
        assert first.status == "GRANTED"
        assert counting.call_count == 1

        second = run(_ensure_access(employee["id"], workspace.id))
    finally:
        _restore_provider()

    assert second.status == "GRANTED"
    assert counting.call_count == 1  # unchanged — no second provider call


def test_granted_attempt_count_unchanged_on_second_call(employee, workspace):
    run(_ensure_access(employee["id"], workspace.id))
    first = run(_get_grant_row(employee["id"], workspace.id))
    run(_ensure_access(employee["id"], workspace.id))
    second = run(_get_grant_row(employee["id"], workspace.id))
    assert first.attempt_count == second.attempt_count == 1


def test_granted_same_row_returned(employee, workspace):
    first = run(_ensure_access(employee["id"], workspace.id))
    second = run(_ensure_access(employee["id"], workspace.id))
    assert first.id == second.id
    assert run(_count_grants(employee["id"], workspace.id)) == 1


def test_failed_retry_uses_same_row(employee, workspace):
    _patch_provider(lambda name: MockWorkspaceProvider(simulate_failure=True))
    try:
        first = run(_ensure_access(employee["id"], workspace.id))
    finally:
        _restore_provider()

    second = run(_ensure_access(employee["id"], workspace.id))  # default provider: succeeds
    assert first.id == second.id
    assert run(_count_grants(employee["id"], workspace.id)) == 1


def test_failed_retry_increments_attempt_count(employee, workspace):
    _patch_provider(lambda name: MockWorkspaceProvider(simulate_failure=True))
    try:
        run(_ensure_access(employee["id"], workspace.id))
    finally:
        _restore_provider()

    run(_ensure_access(employee["id"], workspace.id))
    grant = run(_get_grant_row(employee["id"], workspace.id))
    assert grant.attempt_count == 2


def test_failed_retry_success_becomes_granted(employee, workspace):
    _patch_provider(lambda name: MockWorkspaceProvider(simulate_failure=True))
    try:
        run(_ensure_access(employee["id"], workspace.id))
    finally:
        _restore_provider()

    grant = run(_ensure_access(employee["id"], workspace.id))  # default: succeeds
    assert grant.status == "GRANTED"
    assert grant.last_error is None


def test_failed_retry_failure_remains_failed_with_updated_error(employee, workspace):
    _patch_provider(lambda name: MockWorkspaceProvider(simulate_failure=True))
    try:
        run(_ensure_access(employee["id"], workspace.id))

        class DifferentFailure:
            async def grant_access(self, *, employee_email, workspace):
                from app.services.workspace_provider import WorkspaceGrantResult

                return WorkspaceGrantResult(success=False, error="a different failure reason")

        _patch_provider(lambda name: DifferentFailure())
        grant = run(_ensure_access(employee["id"], workspace.id))
    finally:
        _restore_provider()

    assert grant.status == "FAILED"
    assert grant.last_error == "a different failure reason"
    assert grant.attempt_count == 2


# =====================================================================
# PENDING
# =====================================================================


async def _insert_pending_grant(employee_id: str, workspace_integration_id: str) -> WorkspaceAccessGrant:
    async with AsyncSessionLocal() as db:
        grant = WorkspaceAccessGrant(
            employee_id=employee_id, workspace_integration_id=workspace_integration_id, status="PENDING"
        )
        db.add(grant)
        await db.commit()
        await db.refresh(grant)
        return grant


def test_existing_pending_does_not_create_second_row(employee, workspace):
    run(_insert_pending_grant(employee["id"], workspace.id))
    run(_ensure_access(employee["id"], workspace.id))
    assert run(_count_grants(employee["id"], workspace.id)) == 1


def test_existing_pending_resolves_via_documented_retry_behavior(employee, workspace):
    """Documented behavior (see workspace_access_service.py's module
    docstring): a PENDING row found by ensure_access can only mean a
    prior call was created but never finished (this is a synchronous,
    in-process design with no background worker to pick it up later) —
    so the only safe action is to attempt the provider call now, exactly
    like a FAILED row. This test proves that documented choice, not an
    accident."""
    stale = run(_insert_pending_grant(employee["id"], workspace.id))
    assert stale.attempt_count == 0

    grant = run(_ensure_access(employee["id"], workspace.id))
    assert grant.id == stale.id
    assert grant.status == "GRANTED"
    assert grant.attempt_count == 1


def test_unique_constraint_still_respected(employee, workspace):
    run(_insert_pending_grant(employee["id"], workspace.id))

    async def insert_duplicate():
        async with AsyncSessionLocal() as db:
            dup = WorkspaceAccessGrant(employee_id=employee["id"], workspace_integration_id=workspace.id)
            db.add(dup)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                raise

    with pytest.raises(IntegrityError):
        run(insert_duplicate())


# =====================================================================
# Isolation — a provider failure must touch WorkspaceAccessGrant only
# =====================================================================


def test_workspace_access_service_module_has_no_reference_to_quest_or_capability_domain():
    """Static/architecture check: the module must not even import the
    names it must never mutate — proof by construction that no code path
    here can touch them, not just an assertion that today's code
    happens not to."""
    import app.services.workspace_access_service as mod

    forbidden_names = {
        "QuestAttempt",
        "OnboardingSession",
        "CapabilityEvidence",
        "CapabilityProfile",
        "Recommendation",
        "quest_evaluation_service",
        "capability_aggregation",
        "recommendation_persistence",
    }
    assert forbidden_names.isdisjoint(vars(mod).keys())


def test_provider_failure_does_not_touch_quest_onboarding_capability_or_recommendation_state(
    client, org_id
):
    dept = client.post(
        "/api/v1/departments",
        json={"organization_id": org_id, "name": f"WS Isolation Dept {next(_dept_counter)}"},
    ).json()
    isolated_employee = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": dept["id"],
            "full_name": "Isolation Test Employee",
            "email": f"workspace-isolation-{next(_email_counter)}@kowri.test",
        },
    ).json()
    employee_id = isolated_employee["id"]

    capability_ids = {c["key"]: c["id"] for c in client.get("/api/v1/capabilities").json()}
    quest = client.post(
        "/api/v1/quests",
        json={
            "title": "Isolation test quest",
            "description": "A real workplace problem used only to exercise isolation.",
            "quest_type": "INVESTIGATE",
            "workspace_type": "INVESTIGATION",
        },
    ).json()
    qid = quest["id"]
    client.post(
        f"/api/v1/quests/{qid}/tasks",
        json={"title": "Identify the affected service", "task_type": "INVESTIGATE", "required": False},
    )
    client.post(
        f"/api/v1/quests/{qid}/evidence",
        json={"title": "Latency metrics", "evidence_type": "METRICS", "content": {}},
    )
    client.post(
        f"/api/v1/quests/{qid}/evaluation-criteria",
        json={
            "name": "Correct affected service",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "checkout-service",
            "max_score": 50,
        },
    )
    client.post(
        f"/api/v1/quests/{qid}/capabilities",
        json={"capability_id": capability_ids["troubleshooting"], "weight": 1.0},
    )
    client.post(
        f"/api/v1/quests/{qid}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee_id},
    )
    assert client.post(f"/api/v1/quests/{qid}/publish").status_code == 200

    attempt = client.post(
        "/api/v1/quest-attempts", json={"quest_id": qid, "employee_id": employee_id}
    ).json()
    aid = attempt["id"]
    client.patch(
        f"/api/v1/quest-attempts/{aid}",
        json={
            "employee_id": employee_id,
            "findings": "Latency spiked sharply.",
            "reasoning": "Lines up with a recent deploy that introduced a slow query.",
            "solution": "checkout-service is the affected service.",
        },
    )
    assert client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": employee_id}).status_code == 200
    assert (
        client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": employee_id}).status_code
        == 200
    )

    # Touch onboarding + recommendation so both have real rows too.
    client.get(f"/api/v1/onboarding/bundle/{employee_id}")
    client.get(f"/api/v1/employees/{employee_id}/next-quest")

    async def snapshot():
        async with AsyncSessionLocal() as db:
            count = await db.execute(
                select(func.count()).select_from(Recommendation).where(Recommendation.employee_id == employee_id)
            )
            return count.scalar_one()

    attempt_before = client.get(f"/api/v1/quest-attempts/{aid}", params={"employee_id": employee_id}).json()
    bundle_before = client.get(f"/api/v1/onboarding/bundle/{employee_id}").json()["session"]
    capabilities_before = client.get(f"/api/v1/employees/{employee_id}/capabilities").json()
    recommendation_count_before = run(snapshot())

    # Now force a workspace provider failure for this same employee.
    integration = run(_create_integration(dept["id"]))
    _patch_provider(lambda name: MockWorkspaceProvider(simulate_failure=True))
    try:
        grant = run(_ensure_access(employee_id, integration.id))
    finally:
        _restore_provider()
    assert grant.status == "FAILED"

    attempt_after = client.get(f"/api/v1/quest-attempts/{aid}", params={"employee_id": employee_id}).json()
    bundle_after = client.get(f"/api/v1/onboarding/bundle/{employee_id}").json()["session"]
    capabilities_after = client.get(f"/api/v1/employees/{employee_id}/capabilities").json()
    recommendation_count_after = run(snapshot())

    assert attempt_before == attempt_after
    assert bundle_before == bundle_after
    assert capabilities_after == capabilities_before
    assert recommendation_count_after == recommendation_count_before


# =====================================================================
# Security
# =====================================================================


def test_grant_result_has_no_credential_shaped_fields():
    from app.services.workspace_provider import WorkspaceGrantResult

    forbidden = {"credentials", "tokens", "access_token", "refresh_token", "client_secret", "private_key"}
    field_names = set(WorkspaceGrantResult.__dataclass_fields__.keys())
    assert field_names.isdisjoint(forbidden)


def test_employee_safe_schema_still_excludes_provider_internals():
    from app.schemas.workspace_access import EmployeeWorkspaceAccess

    forbidden = {"external_ref", "provider", "provider_ref", "last_error", "attempt_count"}
    assert set(EmployeeWorkspaceAccess.model_fields.keys()).isdisjoint(forbidden)


def test_not_found_errors_are_caller_errors_not_provider_failures():
    with pytest.raises(EmployeeNotFoundError):
        run(_ensure_access("not-a-real-employee", "not-a-real-workspace"))


def test_workspace_not_found_is_a_caller_error(employee):
    with pytest.raises(WorkspaceIntegrationNotFoundError):
        run(_ensure_access(employee["id"], "not-a-real-workspace"))


# =====================================================================
# Concurrency
# =====================================================================


def test_concurrent_calls_do_not_create_duplicate_grant_rows(employee, workspace):
    """SQLite (this project's dev/test database) serializes writes at the
    connection/file level and its async driver can surface that
    contention as a raw `MissingGreenlet`/`OperationalError` rather than
    the clean `IntegrityError` `ensure_access` is written to catch and
    recover from — a known class of artifact in this exact stack (see
    quest_evaluation_service.py's own comments on the same failure mode
    for a concurrent evaluate() race). That means this test cannot prove
    true multi-connection race safety the way Postgres row-level locking
    would in production; see this module's docstring and Phase 8C's
    final report for that documented limitation.

    What this test DOES prove, honestly: regardless of whether either
    concurrent call raised an environment-level SQLite artifact, at most
    one grant row exists afterward — the unique constraint holds even
    under contention, checked here via a fresh query rather than by
    trusting either call's return value."""

    async def run_both():
        return await asyncio.gather(
            _ensure_access(employee["id"], workspace.id),
            _ensure_access(employee["id"], workspace.id),
            return_exceptions=True,
        )

    run(run_both())
    assert run(_count_grants(employee["id"], workspace.id)) <= 1


def test_concurrent_calls_final_state_is_a_single_resolved_grant(employee, workspace):
    """Documents, rather than asserts away, the known limitation: under
    true concurrency it is architecturally possible for both calls to
    observe PENDING before either finishes and each call the provider
    once (Phase 8C has no row-level locking). What IS guaranteed and
    checked here is the invariant that matters most: exactly one grant
    row exists afterward, and it ends in a resolved (non-PENDING)
    state — never two rows, and never stuck."""

    async def run_both():
        return await asyncio.gather(
            _ensure_access(employee["id"], workspace.id),
            _ensure_access(employee["id"], workspace.id),
            return_exceptions=True,
        )

    run(run_both())
    grant = run(_get_grant_row(employee["id"], workspace.id))
    assert grant is not None
    assert grant.status in ("GRANTED", "FAILED")

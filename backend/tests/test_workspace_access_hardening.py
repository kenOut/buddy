"""Phase 8F-3 backend tests: workspace-access core hardening.

Deliberately does NOT re-test what Phase 8C/8D/8E's test files already
cover exhaustively (first grant, existing-GRANTED short-circuit, FAILED
retry, attempt-count/error persistence, no-duplicate-rows, readiness
invariants, the golden failure-isolation test, cross-employee
isolation) — see test_workspace_access_service.py, test_readiness_
service.py, and test_employee_workspace_access_api.py for those. This
file covers only what Phase 8F-3 actually adds or newly verifies:

  1. The `SELECT ... FOR UPDATE` mechanics added to `_get_grant`/
     `ensure_access` (new code path this stage).
  2. That observing onboarding-completion repeatedly, on its own, never
     creates a grant — only a Quest completion ever triggers anything
     (this was already true, but never had an explicit regression test
     naming it).
  3. That repeatedly fetching the employee-safe workspace-access read
     endpoint never creates or mutates a grant, proven explicitly rather
     than only implied by get_employee_access's docstring.
  4. A re-verification of the SQLite concurrency limitation under the
     NEW locking code, with the same honest documentation discipline as
     Phase 8C's equivalent test — proving "at most one row," not
     claiming "provider called exactly once."

Runs against its own isolated SQLite file, same convention as the other
test_*.py modules.
"""

import asyncio
import itertools
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_workspace_access_hardening.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import WorkspaceAccessGrant, WorkspaceIntegration  # noqa: E402
from app.services.workspace_access_service import _get_grant, ensure_access  # noqa: E402

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
        json={"organization_id": org_id, "name": f"Hardening Dept {next(_dept_counter)}"},
    ).json()


@pytest.fixture
def employee(client, org_id, department):
    return client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "full_name": "Hardening Test Employee",
            "email": f"hardening-{next(_email_counter)}@kowri.test",
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


async def _count_grants_for_employee(employee_id: str) -> int:
    async with AsyncSessionLocal() as db:
        stmt = select(func.count()).select_from(WorkspaceAccessGrant).where(
            WorkspaceAccessGrant.employee_id == employee_id
        )
        result = await db.execute(stmt)
        return result.scalar_one()


# =====================================================================
# FOR UPDATE mechanics
# =====================================================================


def test_for_update_fetch_executes_cleanly_on_sqlite(employee, department):
    """SQLite silently drops FOR UPDATE (verified separately by
    inspection during implementation) — this proves the query still
    executes without error rather than assuming it."""
    integration = run(_create_integration(department["id"]))

    async def fetch_locked():
        async with AsyncSessionLocal() as db:
            return await _get_grant(db, employee["id"], integration.id, for_update=True)

    result = run(fetch_locked())
    assert result is None  # no grant exists yet — just proving the call doesn't raise


def test_ensure_access_still_works_end_to_end_with_locked_fetch(employee, department):
    """The for_update=True fetch is now on ensure_access's hot path by
    default — confirm the ordinary single-caller flow is completely
    unaffected."""

    async def call():
        async with AsyncSessionLocal() as db:
            return await ensure_access(db, employee["id"], (await _create_integration(department["id"])).id)

    grant = run(call())
    assert grant.status == "GRANTED"


# =====================================================================
# Repeated observation without a trigger — nothing should happen
# =====================================================================


def test_repeated_onboarding_completion_observation_alone_creates_no_grant(client, employee, department):
    """Onboarding completion is observed (GET bundle, PATCH scene to
    completion) multiple times — with no Quest ever completed, nothing
    should ever call check_and_trigger, because only quest_evaluation_
    service.evaluate_attempt does that. Proves the trigger boundary is
    exactly where it's documented to be, not accidentally reachable from
    the onboarding-scene endpoints."""
    run(_create_integration(department["id"]))

    bundle = client.get(f"/api/v1/onboarding/bundle/{employee['id']}").json()
    session_id = bundle["session"]["id"]

    for _ in range(3):
        res = client.patch(
            f"/api/v1/onboarding/sessions/{session_id}", json={"current_scene": "completion"}
        )
        assert res.status_code == 200
        client.get(f"/api/v1/onboarding/bundle/{employee['id']}")

    assert run(_count_grants_for_employee(employee["id"])) == 0


# =====================================================================
# Repeated employee-facing GET — never creates or mutates a grant
# =====================================================================


def test_repeated_workspace_access_get_never_creates_a_grant(client, employee, department):
    run(_create_integration(department["id"]))

    for _ in range(5):
        res = client.get(f"/api/v1/employees/{employee['id']}/workspace-access")
        assert res.status_code == 200
        assert res.json()["status"] == "NOT_CONFIGURED"

    assert run(_count_grants_for_employee(employee["id"])) == 0


def test_repeated_workspace_access_get_never_mutates_an_existing_grant(client, employee, department):
    integration = run(_create_integration(department["id"]))

    async def grant_once():
        async with AsyncSessionLocal() as db:
            return await ensure_access(db, employee["id"], integration.id)

    first = run(grant_once())
    assert first.status == "GRANTED"
    assert first.attempt_count == 1

    for _ in range(5):
        res = client.get(f"/api/v1/employees/{employee['id']}/workspace-access")
        assert res.status_code == 200
        assert res.json()["status"] == "GRANTED"

    async def fetch():
        async with AsyncSessionLocal() as db:
            return await _get_grant(db, employee["id"], integration.id)

    final = run(fetch())
    assert final.attempt_count == 1  # unchanged — reads never touch it
    assert run(_count_grants_for_employee(employee["id"])) == 1


# =====================================================================
# Concurrency — re-verified under the new locking code
# =====================================================================


def test_concurrent_ensure_access_still_yields_at_most_one_grant_row(employee, department):
    """Re-verification of Phase 8C's concurrency invariant against the
    NEW for_update=True code path. Same honest limitation as before:
    SQLite (this project's dev/test database) serializes writes at the
    connection/file level and does not implement row-level locking at
    all, so FOR UPDATE compiles to nothing here — this test cannot prove
    Postgres row-locking behavior, only that the unique constraint plus
    IntegrityError recovery still holds under contention. See
    ensure_access's own docstring for the precise, non-overstated
    concurrency guarantee."""
    integration = run(_create_integration(department["id"]))

    async def call():
        async with AsyncSessionLocal() as db:
            return await ensure_access(db, employee["id"], integration.id)

    async def run_both():
        return await asyncio.gather(call(), call(), return_exceptions=True)

    run(run_both())
    assert run(_count_grants_for_employee(employee["id"])) <= 1

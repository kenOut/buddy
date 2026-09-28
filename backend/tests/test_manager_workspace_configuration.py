"""Phase 8G backend tests: manager/admin workspace configuration —
GET/POST/PATCH /departments/{department_id}/workspace.

Covers authentication/authorization, department existence, create,
duplicate prevention, update (including activate/deactivate), provider
validation, cross-department isolation, and that configuration changes
never mutate existing WorkspaceAccessGrant rows.

Runs against its own isolated SQLite file, same convention as the other
test_*.py modules.
"""

import asyncio
import itertools
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_manager_workspace_configuration.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import WorkspaceAccessGrant, WorkspaceIntegration  # noqa: E402
from app.services.workspace_access_service import ensure_access  # noqa: E402

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
        json={"organization_id": org_id, "name": f"WS Config Dept {next(_dept_counter)}"},
    ).json()


def _payload(**overrides):
    defaults = dict(
        provider="google_drive",
        external_ref="drive-folder-abc123",
        display_name="Engineering Workspace",
        workspace_link="https://drive.google.com/drive/folders/abc123",
    )
    defaults.update(overrides)
    return defaults


# =====================================================================
# Authentication / authorization
# =====================================================================


def test_unauthenticated_get_denied(department):
    with TestClient(app) as anon:
        res = anon.get(f"/api/v1/departments/{department['id']}/workspace")
        assert res.status_code == 401


def test_unauthenticated_create_denied(department):
    with TestClient(app) as anon:
        res = anon.post(f"/api/v1/departments/{department['id']}/workspace", json=_payload())
        assert res.status_code == 401


def test_unauthenticated_update_denied(department):
    with TestClient(app) as anon:
        res = anon.patch(f"/api/v1/departments/{department['id']}/workspace", json={"active": False})
        assert res.status_code == 401


def test_employee_facing_session_cannot_reach_manager_endpoint():
    """No employee-facing session mechanism exists in this app at all
    (confirmed throughout Phase 8A-8F) — the only "session" an employee
    ever has is the plain onboarding bundle fetch, which carries no
    cookie/token whatsoever. Proving this endpoint requires the admin
    session cookie specifically (not just "some session") is exactly
    what the unauthenticated tests above already prove: a client that
    has only ever called employee-facing endpoints (never /admin/login)
    is indistinguishable from anonymous here, and is denied identically."""
    with TestClient(app) as employee_facing:
        employee_facing.get("/api/v1/onboarding/bundle/demo")  # the one thing an employee session ever does
        res = employee_facing.get("/api/v1/departments")
        assert res.status_code == 401


def test_authorized_admin_access_succeeds(client, department):
    res = client.get(f"/api/v1/departments/{department['id']}/workspace")
    assert res.status_code == 200


# =====================================================================
# Department existence
# =====================================================================


def test_get_workspace_for_nonexistent_department_404s(client):
    res = client.get("/api/v1/departments/not-a-real-department/workspace")
    assert res.status_code == 404


def test_create_workspace_for_nonexistent_department_404s(client):
    res = client.post("/api/v1/departments/not-a-real-department/workspace", json=_payload())
    assert res.status_code == 404


def test_get_workspace_for_existing_department_with_none_configured_returns_null(client, department):
    res = client.get(f"/api/v1/departments/{department['id']}/workspace")
    assert res.status_code == 200
    assert res.json() is None


# =====================================================================
# Create
# =====================================================================


def test_create_workspace(client, department):
    res = client.post(f"/api/v1/departments/{department['id']}/workspace", json=_payload())
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["department_id"] == department["id"]
    assert body["provider"] == "google_drive"
    assert body["display_name"] == "Engineering Workspace"
    assert body["active"] is True


def test_created_workspace_is_returned_by_get(client, department):
    client.post(f"/api/v1/departments/{department['id']}/workspace", json=_payload())
    res = client.get(f"/api/v1/departments/{department['id']}/workspace")
    assert res.status_code == 200
    assert res.json()["department_id"] == department["id"]


def test_duplicate_create_is_rejected(client, department):
    first = client.post(f"/api/v1/departments/{department['id']}/workspace", json=_payload())
    assert first.status_code == 201
    second = client.post(f"/api/v1/departments/{department['id']}/workspace", json=_payload())
    assert second.status_code == 409


# =====================================================================
# Update
# =====================================================================


def test_update_workspace_fields(client, department):
    client.post(f"/api/v1/departments/{department['id']}/workspace", json=_payload())
    res = client.patch(
        f"/api/v1/departments/{department['id']}/workspace",
        json={"display_name": "Renamed Workspace"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["display_name"] == "Renamed Workspace"
    # Untouched fields survive the partial update.
    assert res.json()["provider"] == "google_drive"


def test_update_nonexistent_workspace_404s(client, department):
    res = client.patch(f"/api/v1/departments/{department['id']}/workspace", json={"active": False})
    assert res.status_code == 404


def test_deactivate_workspace(client, department):
    client.post(f"/api/v1/departments/{department['id']}/workspace", json=_payload())
    res = client.patch(f"/api/v1/departments/{department['id']}/workspace", json={"active": False})
    assert res.status_code == 200
    assert res.json()["active"] is False


def test_reactivate_workspace(client, department):
    client.post(f"/api/v1/departments/{department['id']}/workspace", json=_payload())
    client.patch(f"/api/v1/departments/{department['id']}/workspace", json={"active": False})
    res = client.patch(f"/api/v1/departments/{department['id']}/workspace", json={"active": True})
    assert res.status_code == 200
    assert res.json()["active"] is True


def test_repeated_update_does_not_create_a_second_row(client, department):
    client.post(f"/api/v1/departments/{department['id']}/workspace", json=_payload())
    client.patch(f"/api/v1/departments/{department['id']}/workspace", json={"display_name": "A"})
    client.patch(f"/api/v1/departments/{department['id']}/workspace", json={"display_name": "B"})
    client.patch(f"/api/v1/departments/{department['id']}/workspace", json={"display_name": "C"})

    async def count():
        async with AsyncSessionLocal() as db:
            from sqlalchemy import func, select

            result = await db.execute(
                select(func.count())
                .select_from(WorkspaceIntegration)
                .where(WorkspaceIntegration.department_id == department["id"])
            )
            return result.scalar_one()

    assert run(count()) == 1


# =====================================================================
# Validation
# =====================================================================


def test_invalid_provider_rejected_on_create(client, department):
    res = client.post(
        f"/api/v1/departments/{department['id']}/workspace", json=_payload(provider="not-a-real-provider")
    )
    assert res.status_code == 422


def test_invalid_provider_rejected_on_update(client, department):
    client.post(f"/api/v1/departments/{department['id']}/workspace", json=_payload())
    res = client.patch(
        f"/api/v1/departments/{department['id']}/workspace", json={"provider": "not-a-real-provider"}
    )
    assert res.status_code == 422


def test_missing_required_field_rejected(client, department):
    payload = _payload()
    del payload["display_name"]
    res = client.post(f"/api/v1/departments/{department['id']}/workspace", json=payload)
    assert res.status_code == 422


def test_mock_is_not_a_valid_stored_provider_value(client, department):
    """"mock" selects a provider IMPLEMENTATION app-wide via
    settings.workspace_provider — it is never a legitimate value for a
    specific department's stored WorkspaceIntegration.provider column
    (see models/workspace_integration.py's WORKSPACE_PROVIDERS). The
    manager UI must offer only real, storable provider values."""
    res = client.post(f"/api/v1/departments/{department['id']}/workspace", json=_payload(provider="mock"))
    assert res.status_code == 422


# =====================================================================
# Isolation
# =====================================================================


def test_one_departments_workspace_does_not_leak_into_another(client, org_id, department):
    other_department = client.post(
        "/api/v1/departments",
        json={"organization_id": org_id, "name": f"WS Config Dept {next(_dept_counter)}"},
    ).json()

    client.post(
        f"/api/v1/departments/{department['id']}/workspace",
        json=_payload(display_name="Department A Workspace"),
    )

    a = client.get(f"/api/v1/departments/{department['id']}/workspace").json()
    b = client.get(f"/api/v1/departments/{other_department['id']}/workspace").json()

    assert a["display_name"] == "Department A Workspace"
    assert b is None


# =====================================================================
# Existing grants are untouched by configuration changes
# =====================================================================


def test_editing_configuration_does_not_mutate_existing_grants(client, org_id, department):
    integration_res = client.post(
        f"/api/v1/departments/{department['id']}/workspace", json=_payload()
    ).json()

    employee = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "full_name": "Grant Isolation Employee",
            "email": f"ws-config-grant-{next(_email_counter)}@kowri.test",
        },
    ).json()

    async def grant_and_read():
        async with AsyncSessionLocal() as db:
            grant = await ensure_access(db, employee["id"], integration_res["id"])
            return grant.status, grant.attempt_count, grant.provider_ref, grant.granted_at

    status_before, attempts_before, ref_before, granted_before = run(grant_and_read())
    assert status_before == "GRANTED"

    # Edit the configuration several times, including deactivating it.
    client.patch(
        f"/api/v1/departments/{department['id']}/workspace", json={"display_name": "Renamed"}
    )
    client.patch(f"/api/v1/departments/{department['id']}/workspace", json={"active": False})
    client.patch(f"/api/v1/departments/{department['id']}/workspace", json={"active": True})

    async def read_grant():
        async with AsyncSessionLocal() as db:
            from app.models import WorkspaceAccessGrant as WAG
            from sqlalchemy import select

            result = await db.execute(
                select(WAG).where(
                    WAG.employee_id == employee["id"], WAG.workspace_integration_id == integration_res["id"]
                )
            )
            return result.scalar_one()

    grant_after = run(read_grant())
    assert grant_after.status == status_before
    assert grant_after.attempt_count == attempts_before
    assert grant_after.provider_ref == ref_before
    assert grant_after.granted_at == granted_before


def test_deactivating_configuration_does_not_delete_the_integration_row_or_grants(client, org_id, department):
    """Deactivating must be reversible state, not destructive."""
    integration_res = client.post(
        f"/api/v1/departments/{department['id']}/workspace", json=_payload()
    ).json()
    employee = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "full_name": "Deactivate Test Employee",
            "email": f"ws-config-deactivate-{next(_email_counter)}@kowri.test",
        },
    ).json()
    run(_grant(employee["id"], integration_res["id"]))

    client.patch(f"/api/v1/departments/{department['id']}/workspace", json={"active": False})

    async def counts():
        async with AsyncSessionLocal() as db:
            from sqlalchemy import func, select

            grants = await db.execute(
                select(func.count()).select_from(WorkspaceAccessGrant).where(
                    WorkspaceAccessGrant.employee_id == employee["id"]
                )
            )
            integrations = await db.execute(
                select(func.count())
                .select_from(WorkspaceIntegration)
                .where(WorkspaceIntegration.id == integration_res["id"])
            )
            return grants.scalar_one(), integrations.scalar_one()

    grant_count, integration_count = run(counts())
    assert grant_count == 1
    assert integration_count == 1


async def _grant(employee_id, workspace_integration_id):
    async with AsyncSessionLocal() as db:
        return await ensure_access(db, employee_id, workspace_integration_id)

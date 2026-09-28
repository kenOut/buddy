"""Phase 8E backend tests: the employee-safe workspace-access read API,
GET /employees/{employee_id}/workspace-access.

Covers the four API-level statuses (GRANTED/PENDING/FAILED/
NOT_CONFIGURED), the security boundary (never leaks external_ref/
provider/provider_ref/last_error/attempt_count/credentials/tokens),
404 for a non-existent employee, and per-employee isolation (one
employee's grant never leaks into another's response).

This endpoint lives in capabilities.py (not employees.py) specifically
because it must stay reachable without a manager login — see
app/api/v1/router.py's own comment on which routers are gated. No new
authentication is introduced; ownership here means "the response is
scoped strictly to the employee_id in the URL," verified directly
below, matching this project's existing employee-facing endpoints
(get_employee_capabilities, get_development_journey, etc.), none of
which have any stronger identity check either.

Runs against its own isolated SQLite file, same convention as the other
test_*.py modules.
"""

import asyncio
import itertools
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_employee_workspace_access_api.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.services.workspace_access_service as was_mod  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import WorkspaceAccessGrant, WorkspaceIntegration  # noqa: E402
from app.services.workspace_provider import MockWorkspaceProvider, get_workspace_provider  # noqa: E402

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
        json={"organization_id": org_id, "name": f"WS API Dept {next(_dept_counter)}"},
    ).json()


@pytest.fixture
def employee(client, org_id, department):
    return client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "full_name": "Workspace API Test Employee",
            "email": f"workspace-api-{next(_email_counter)}@kowri.test",
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


async def _ensure_access(employee_id: str, workspace_integration_id: str) -> WorkspaceAccessGrant:
    async with AsyncSessionLocal() as db:
        from app.services.workspace_access_service import ensure_access

        return await ensure_access(db, employee_id, workspace_integration_id)


async def _insert_pending_grant(employee_id: str, workspace_integration_id: str) -> None:
    async with AsyncSessionLocal() as db:
        db.add(
            WorkspaceAccessGrant(
                employee_id=employee_id, workspace_integration_id=workspace_integration_id, status="PENDING"
            )
        )
        await db.commit()


def _patch_provider(factory):
    was_mod.get_workspace_provider = factory


def _restore_provider():
    was_mod.get_workspace_provider = get_workspace_provider


_FORBIDDEN_FIELDS = {
    "external_ref",
    "provider",
    "provider_ref",
    "last_error",
    "attempt_count",
    "credentials",
    "tokens",
    "access_token",
    "refresh_token",
}


def _assert_response_is_safe(body: dict):
    assert set(body.keys()) == {"status", "workspace_name", "workspace_link"}
    assert _FORBIDDEN_FIELDS.isdisjoint(body.keys())
    # Belt-and-suspenders: none of the forbidden values should appear
    # anywhere in the serialized body, even under an unexpected key.
    serialized = str(body)
    for forbidden in _FORBIDDEN_FIELDS:
        assert forbidden not in serialized


# =====================================================================
# The four statuses
# =====================================================================


def test_granted_response(client, employee, department):
    integration = run(_create_integration(department["id"]))
    run(_ensure_access(employee["id"], integration.id))

    res = client.get(f"/api/v1/employees/{employee['id']}/workspace-access")
    assert res.status_code == 200, res.text
    body = res.json()
    _assert_response_is_safe(body)
    assert body["status"] == "GRANTED"
    assert body["workspace_name"] == "Engineering Workspace"
    assert body["workspace_link"] == "https://drive.google.com/drive/folders/abc123"


def test_failed_response(client, employee, department):
    integration = run(_create_integration(department["id"]))
    _patch_provider(lambda name: MockWorkspaceProvider(simulate_failure=True))
    try:
        run(_ensure_access(employee["id"], integration.id))
    finally:
        _restore_provider()

    res = client.get(f"/api/v1/employees/{employee['id']}/workspace-access")
    assert res.status_code == 200, res.text
    body = res.json()
    _assert_response_is_safe(body)
    assert body["status"] == "FAILED"
    assert body["workspace_name"] == "Engineering Workspace"
    assert body["workspace_link"] is None


def test_pending_response(client, employee, department):
    integration = run(_create_integration(department["id"]))
    run(_insert_pending_grant(employee["id"], integration.id))

    res = client.get(f"/api/v1/employees/{employee['id']}/workspace-access")
    assert res.status_code == 200, res.text
    body = res.json()
    _assert_response_is_safe(body)
    assert body["status"] == "PENDING"
    assert body["workspace_link"] is None


def test_not_configured_when_no_integration(client, employee):
    res = client.get(f"/api/v1/employees/{employee['id']}/workspace-access")
    assert res.status_code == 200, res.text
    body = res.json()
    _assert_response_is_safe(body)
    assert body["status"] == "NOT_CONFIGURED"
    assert body["workspace_name"] is None
    assert body["workspace_link"] is None


def test_not_configured_when_integration_inactive(client, employee, department):
    run(_create_integration(department["id"], active=False))
    res = client.get(f"/api/v1/employees/{employee['id']}/workspace-access")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "NOT_CONFIGURED"


def test_not_configured_when_integration_exists_but_no_grant_yet(client, employee, department):
    """Integration is configured, but nothing has triggered a grant for
    this employee yet — still NOT_CONFIGURED, never a fabricated
    PENDING/FAILED, and never exposes anything about readiness."""
    run(_create_integration(department["id"]))
    res = client.get(f"/api/v1/employees/{employee['id']}/workspace-access")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "NOT_CONFIGURED"
    assert body["workspace_name"] == "Engineering Workspace"  # named, since it does exist
    assert body["workspace_link"] is None


def test_not_configured_when_employee_has_no_department(client, org_id):
    employee = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "full_name": "Deptless Employee",
            "email": f"workspace-api-deptless-{next(_email_counter)}@kowri.test",
        },
    ).json()
    res = client.get(f"/api/v1/employees/{employee['id']}/workspace-access")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "NOT_CONFIGURED"


# =====================================================================
# Not found / isolation
# =====================================================================


def test_nonexistent_employee_returns_404(client):
    res = client.get("/api/v1/employees/not-a-real-employee/workspace-access")
    assert res.status_code == 404


def test_one_employees_grant_never_leaks_into_anothers_response(client, org_id, department):
    integration = run(_create_integration(department["id"]))

    employee_a = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "full_name": "Isolation Employee A",
            "email": f"workspace-api-a-{next(_email_counter)}@kowri.test",
        },
    ).json()
    employee_b = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "full_name": "Isolation Employee B",
            "email": f"workspace-api-b-{next(_email_counter)}@kowri.test",
        },
    ).json()

    run(_ensure_access(employee_a["id"], integration.id))
    # employee_b deliberately has no grant at all.

    a_res = client.get(f"/api/v1/employees/{employee_a['id']}/workspace-access")
    b_res = client.get(f"/api/v1/employees/{employee_b['id']}/workspace-access")

    assert a_res.json()["status"] == "GRANTED"
    assert b_res.json()["status"] == "NOT_CONFIGURED"


# =====================================================================
# Never requires manager login
# =====================================================================


def test_workspace_access_endpoint_never_requires_login(employee):
    with TestClient(app) as anon:
        res = anon.get(f"/api/v1/employees/{employee['id']}/workspace-access")
        assert res.status_code == 200

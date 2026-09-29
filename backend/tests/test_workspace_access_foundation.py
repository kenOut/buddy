"""Phase 8B backend tests: Workspace Access Automation — the pure
database/domain foundation only.

This stage adds three things and nothing else:
  1. QuestAssignment.required (a new column on an existing model)
  2. WorkspaceIntegration (a new model)
  3. WorkspaceAccessGrant (a new model)

No ReadinessService, no WorkspaceProvider, no trigger wired into
evaluate_attempt(), and no API endpoints exist for the new models yet
(Phase 8C) — so these tests exercise the ORM layer directly via
AsyncSessionLocal, the same precedent already used in
test_quest_assignments.py for model-level assertions the public API
doesn't expose (see its `delete_and_check` test).

Runs against its own isolated SQLite file, same convention as the other
test_*.py modules.
"""

import asyncio
import itertools
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_workspace_access_foundation.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import QuestAssignment, WorkspaceAccessGrant, WorkspaceIntegration  # noqa: E402
from app.schemas.workspace_access import EmployeeWorkspaceAccess  # noqa: E402

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
    """A fresh department per test — WorkspaceIntegration.department_id
    is unique, so tests that create an integration must not share a
    department with each other."""
    return client.post(
        "/api/v1/departments",
        json={"organization_id": org_id, "name": f"WS Foundation Dept {next(_dept_counter)}"},
    ).json()


@pytest.fixture
def employee(client, org_id, department):
    return client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "full_name": "Workspace Foundation Employee",
            "email": f"workspace-foundation-{next(_email_counter)}@kowri.test",
        },
    ).json()


@pytest.fixture
def quest(client, org_id, department):
    return client.post(
        "/api/v1/quests",
        json={
            "title": "Workspace Foundation Test Quest",
            "quest_type": "OTHER",
            "workspace_type": "GENERAL",
        },
    ).json()


async def _get_assignment(assignment_id: str) -> QuestAssignment:
    async with AsyncSessionLocal() as db:
        return await db.get(QuestAssignment, assignment_id)


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


async def _create_grant(employee_id: str, workspace_integration_id: str, **overrides) -> WorkspaceAccessGrant:
    defaults = dict(employee_id=employee_id, workspace_integration_id=workspace_integration_id)
    defaults.update(overrides)
    async with AsyncSessionLocal() as db:
        grant = WorkspaceAccessGrant(**defaults)
        db.add(grant)
        await db.commit()
        await db.refresh(grant)
        return grant


# =====================================================================
# 1. QuestAssignment.required
# =====================================================================


def test_existing_assignment_defaults_to_required_false(client, quest, department):
    assignment = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "DEPARTMENT", "department_id": department["id"]},
    ).json()

    row = run(_get_assignment(assignment["id"]))
    assert row.required is False


def test_required_assignment_can_be_persisted(client, quest, department):
    assignment = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "DEPARTMENT", "department_id": department["id"]},
    ).json()

    async def set_required():
        async with AsyncSessionLocal() as db:
            row = await db.get(QuestAssignment, assignment["id"])
            row.required = True
            await db.commit()

    run(set_required())

    row = run(_get_assignment(assignment["id"]))
    assert row.required is True


def test_existing_assignment_behavior_unchanged(client, quest, department):
    """Phase 8C: adding the `required` column must not perturb the
    existing request/response contract for a caller that ignores it
    entirely — the assignment is still created the same way, and
    omitting `required` still means "optional" (Phase 8H-3 exposed the
    column through the API; this test now asserts that exposure's own
    default, not its prior absence)."""
    res = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "DEPARTMENT", "department_id": department["id"]},
    )
    assert res.status_code == 201, res.text
    assert res.json()["required"] is False

    listing = client.get(f"/api/v1/quests/{quest['id']}/assignments")
    assert listing.status_code == 200
    assert len(listing.json()) == 1


# =====================================================================
# 2. WorkspaceIntegration
# =====================================================================


def test_can_create_department_workspace(department):
    integration = run(_create_integration(department["id"]))
    assert integration.id is not None
    assert integration.department_id == department["id"]
    assert integration.display_name == "Engineering Workspace"
    assert integration.workspace_link == "https://drive.google.com/drive/folders/abc123"


def test_department_uniqueness_enforced(department):
    run(_create_integration(department["id"]))

    async def create_second():
        async with AsyncSessionLocal() as db:
            dup = WorkspaceIntegration(
                department_id=department["id"],
                provider="google_drive",
                external_ref="drive-folder-different",
                display_name="Duplicate",
                workspace_link="https://drive.google.com/drive/folders/different",
            )
            db.add(dup)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                raise

    with pytest.raises(IntegrityError):
        run(create_second())


def test_provider_value_is_persisted(department):
    integration = run(_create_integration(department["id"], provider="google_drive"))
    assert integration.provider == "google_drive"


def test_active_defaults_true(department):
    integration = run(_create_integration(department["id"]))
    assert integration.active is True


# =====================================================================
# 3. WorkspaceAccessGrant
# =====================================================================


def test_can_create_grant(employee, department):
    integration = run(_create_integration(department["id"]))
    grant = run(_create_grant(employee["id"], integration.id))
    assert grant.id is not None
    assert grant.employee_id == employee["id"]
    assert grant.workspace_integration_id == integration.id


def test_default_status_is_pending(employee, department):
    integration = run(_create_integration(department["id"]))
    grant = run(_create_grant(employee["id"], integration.id))
    assert grant.status == "PENDING"


def test_attempt_count_starts_at_zero(employee, department):
    integration = run(_create_integration(department["id"]))
    grant = run(_create_grant(employee["id"], integration.id))
    assert grant.attempt_count == 0


def test_granted_status_stores_granted_at(employee, department):
    from datetime import datetime, timezone

    integration = run(_create_integration(department["id"]))
    now = datetime.now(timezone.utc)
    grant = run(_create_grant(employee["id"], integration.id, status="GRANTED", granted_at=now))
    assert grant.status == "GRANTED"
    assert grant.granted_at is not None


def test_failed_status_stores_last_error(employee, department):
    integration = run(_create_integration(department["id"]))
    grant = run(
        _create_grant(
            employee["id"], integration.id, status="FAILED", last_error="Google Drive API timeout"
        )
    )
    assert grant.status == "FAILED"
    assert grant.last_error == "Google Drive API timeout"


def test_provider_ref_can_be_stored(employee, department):
    integration = run(_create_integration(department["id"]))
    grant = run(
        _create_grant(
            employee["id"], integration.id, status="GRANTED", provider_ref="gdrive-permission-xyz789"
        )
    )
    assert grant.provider_ref == "gdrive-permission-xyz789"


def test_revoked_is_valid_status(employee, department):
    integration = run(_create_integration(department["id"]))
    grant = run(_create_grant(employee["id"], integration.id, status="REVOKED"))
    assert grant.status == "REVOKED"


# =====================================================================
# Idempotency — the (employee_id, workspace_integration_id) unique
# constraint is the primary mechanism (see model docstring).
# =====================================================================


def test_same_employee_same_workspace_cannot_create_two_grants(employee, department):
    integration = run(_create_integration(department["id"]))
    run(_create_grant(employee["id"], integration.id))

    async def create_duplicate():
        async with AsyncSessionLocal() as db:
            dup = WorkspaceAccessGrant(employee_id=employee["id"], workspace_integration_id=integration.id)
            db.add(dup)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                raise

    with pytest.raises(IntegrityError):
        run(create_duplicate())


def test_different_employee_same_workspace_is_allowed(client, org_id, department):
    integration = run(_create_integration(department["id"]))
    other_employee = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "full_name": "Second Workspace Foundation Employee",
            "email": f"workspace-foundation-{next(_email_counter)}@kowri.test",
        },
    ).json()

    first_employee = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "full_name": "First Workspace Foundation Employee",
            "email": f"workspace-foundation-{next(_email_counter)}@kowri.test",
        },
    ).json()

    run(_create_grant(first_employee["id"], integration.id))
    second_grant = run(_create_grant(other_employee["id"], integration.id))
    assert second_grant.id is not None


def test_same_employee_different_workspace_is_allowed(client, org_id, employee, department):
    integration_a = run(_create_integration(department["id"]))

    other_department = client.post(
        "/api/v1/departments",
        json={"organization_id": org_id, "name": f"WS Foundation Dept {next(_dept_counter)}"},
    ).json()
    integration_b = run(_create_integration(other_department["id"]))

    run(_create_grant(employee["id"], integration_a.id))
    second_grant = run(_create_grant(employee["id"], integration_b.id))
    assert second_grant.id is not None


# =====================================================================
# Security — the employee-safe schema
# =====================================================================


def test_employee_safe_schema_excludes_operational_and_credential_fields():
    forbidden = {
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
    field_names = set(EmployeeWorkspaceAccess.model_fields.keys())
    assert field_names.isdisjoint(forbidden)
    assert field_names == {"status", "workspace_name", "workspace_link"}

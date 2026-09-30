"""Phase A — Team Entity & Department -> Team Foundation backend tests:
GET/POST /departments/{department_id}/teams.

Covers create, list, empty-department, duplicate-within-department
rejection, same-name-across-departments allowance, missing-department
rejection, real persistence (a fresh session/query, not just what the
creating request returned), the response schema, department-delete
cascade behavior, and the existing admin-session/error conventions
(401/404/409/422).

Runs against its own isolated SQLite file, same convention as the other
test_*.py modules — mirrors test_manager_workspace_configuration.py's
own fixtures, the closest existing precedent for a department-scoped
sub-resource.
"""

import asyncio
import itertools
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_teams.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Department, Team  # noqa: E402

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
def anon_client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def demo_bundle(client):
    return client.get("/api/v1/onboarding/bundle/demo").json()


@pytest.fixture(scope="module")
def org_id(demo_bundle):
    return demo_bundle["employee"]["organization_id"]


@pytest.fixture
def department(client, org_id):
    """A fresh department per test — never reuses the demo Engineering
    department, so team-name collisions between tests are impossible."""
    return client.post(
        "/api/v1/departments",
        json={"organization_id": org_id, "name": f"Team Test Dept {next(_dept_counter)}"},
    ).json()


# =====================================================================
# 1. Create team under a valid department
# =====================================================================


def test_create_team_under_valid_department(client, department):
    res = client.post(
        f"/api/v1/departments/{department['id']}/teams",
        json={"name": "TechOps", "description": "Infrastructure and reliability."},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["name"] == "TechOps"
    assert body["department_id"] == department["id"]
    assert body["description"] == "Infrastructure and reliability."


# =====================================================================
# 2. List teams for a department
# =====================================================================


def test_list_teams_for_department(client, department):
    client.post(f"/api/v1/departments/{department['id']}/teams", json={"name": "TechOps"})
    client.post(f"/api/v1/departments/{department['id']}/teams", json={"name": "Security & IT"})

    res = client.get(f"/api/v1/departments/{department['id']}/teams")
    assert res.status_code == 200
    names = {t["name"] for t in res.json()}
    assert names == {"TechOps", "Security & IT"}


# =====================================================================
# 3. Empty department returns empty team list
# =====================================================================


def test_empty_department_returns_empty_team_list(client, department):
    res = client.get(f"/api/v1/departments/{department['id']}/teams")
    assert res.status_code == 200
    assert res.json() == []


# =====================================================================
# 4. Duplicate team name within the same department rejected
# =====================================================================


def test_duplicate_team_name_within_same_department_rejected(client, department):
    first = client.post(f"/api/v1/departments/{department['id']}/teams", json={"name": "FinOps"})
    assert first.status_code == 201

    second = client.post(f"/api/v1/departments/{department['id']}/teams", json={"name": "FinOps"})
    assert second.status_code == 409


# =====================================================================
# 5. Same team name under different departments allowed
# =====================================================================


def test_same_team_name_under_different_departments_allowed(client, org_id):
    dept_a = client.post(
        "/api/v1/departments", json={"organization_id": org_id, "name": f"Team Test A {next(_dept_counter)}"}
    ).json()
    dept_b = client.post(
        "/api/v1/departments", json={"organization_id": org_id, "name": f"Team Test B {next(_dept_counter)}"}
    ).json()

    res_a = client.post(f"/api/v1/departments/{dept_a['id']}/teams", json={"name": "Security & IT"})
    res_b = client.post(f"/api/v1/departments/{dept_b['id']}/teams", json={"name": "Security & IT"})
    assert res_a.status_code == 201
    assert res_b.status_code == 201
    assert res_a.json()["id"] != res_b.json()["id"]


# =====================================================================
# 6. Missing department rejected
# =====================================================================


def test_create_team_under_missing_department_rejected(client):
    res = client.post("/api/v1/departments/does-not-exist/teams", json={"name": "TechOps"})
    assert res.status_code == 404


def test_list_teams_for_missing_department_rejected(client):
    res = client.get("/api/v1/departments/does-not-exist/teams")
    assert res.status_code == 404


# =====================================================================
# 7. Team persists after session/transaction reload
# =====================================================================


def test_team_persists_after_session_reload(client, department):
    created = client.post(
        f"/api/v1/departments/{department['id']}/teams", json={"name": "Platform Engineering"}
    ).json()

    async def _fetch_in_fresh_session():
        async with AsyncSessionLocal() as db:
            return await db.get(Team, created["id"])

    row = run(_fetch_in_fresh_session())
    assert row is not None
    assert row.name == "Platform Engineering"
    assert row.department_id == department["id"]


# =====================================================================
# 8. Department deletion follows the chosen FK cascade
# =====================================================================


def test_department_deletion_cascades_to_teams(client, department):
    """No DELETE endpoint exists for Department at all (confirmed by
    the Team Architecture Impact Audit) — exercised directly at the
    ORM level, the same technique test_quest_content.py already uses
    to verify Quest's own child-cascade behavior. This is also what
    caught a real bug during Phase A's own implementation: without
    `cascade="all, delete-orphan"` on Department.teams, this commit
    failed with a NOT NULL constraint error instead of cascading,
    because SQLite (this project's dev/test database) never enforces
    FK pragmas — the DB-level ON DELETE CASCADE alone did nothing
    here. See department.py's own comment on the fix."""
    team = client.post(f"/api/v1/departments/{department['id']}/teams", json={"name": "Delivery"}).json()

    async def _delete_department_and_check():
        async with AsyncSessionLocal() as db:
            dept_obj = await db.get(Department, department["id"])
            await db.delete(dept_obj)
            await db.commit()

        async with AsyncSessionLocal() as db:
            return await db.get(Team, team["id"])

    remaining_team = run(_delete_department_and_check())
    assert remaining_team is None


# =====================================================================
# 9. API response schema is correct
# =====================================================================


def test_team_response_schema(client, department):
    res = client.post(
        f"/api/v1/departments/{department['id']}/teams",
        json={"name": "Customer Experience", "description": "Customer-facing product experience."},
    )
    body = res.json()
    assert set(body.keys()) == {
        "id",
        "department_id",
        "name",
        "description",
        "created_at",
        "updated_at",
    }
    assert isinstance(body["id"], str)
    assert isinstance(body["created_at"], str)
    assert isinstance(body["updated_at"], str)


def test_team_without_description_returns_null(client, department):
    res = client.post(f"/api/v1/departments/{department['id']}/teams", json={"name": "TechOps"})
    assert res.json()["description"] is None


# =====================================================================
# 10. Existing error conventions
# =====================================================================


def test_create_team_requires_admin_session(anon_client, department):
    res = anon_client.post(f"/api/v1/departments/{department['id']}/teams", json={"name": "TechOps"})
    assert res.status_code == 401


def test_list_teams_requires_admin_session(anon_client, department):
    res = anon_client.get(f"/api/v1/departments/{department['id']}/teams")
    assert res.status_code == 401


def test_create_team_with_empty_name_rejected(client, department):
    res = client.post(f"/api/v1/departments/{department['id']}/teams", json={"name": ""})
    assert res.status_code == 422


def test_create_team_without_name_rejected(client, department):
    res = client.post(f"/api/v1/departments/{department['id']}/teams", json={})
    assert res.status_code == 422


def test_duplicate_team_error_names_the_department_and_team(client, department):
    client.post(f"/api/v1/departments/{department['id']}/teams", json={"name": "FinOps"})
    res = client.post(f"/api/v1/departments/{department['id']}/teams", json={"name": "FinOps"})
    assert res.status_code == 409
    assert "FinOps" in res.json()["detail"]

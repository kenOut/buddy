"""Tests for PATCH/DELETE /departments/{department_id} — added alongside
the Manager Portal's department "Edit"/"Delete" actions.

Runs against an isolated SQLite file, deleted and recreated each run
(same pattern as test_mission_delete.py).
"""

import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_department_delete.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.config import get_settings  # noqa: E402


@pytest.fixture(scope="module")
def client():
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"
    with TestClient(app) as c:
        c.post("/api/v1/admin/login", json={"password": get_settings().admin_password})
        yield c
    TEST_DB_PATH.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _restore_database_url_after_each_test():
    original = os.environ.get("DATABASE_URL")
    yield
    if original is not None:
        os.environ["DATABASE_URL"] = original


@pytest.fixture(scope="module")
def org_id(client):
    return client.get("/api/v1/onboarding/bundle/demo").json()["employee"]["organization_id"]


def _create_department(client, org_id, *, name):
    res = client.post("/api/v1/departments", json={"organization_id": org_id, "name": name})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_editing_a_department_updates_name_and_description(client, org_id):
    department_id = _create_department(client, org_id, name="Original Name")

    res = client.patch(
        f"/api/v1/departments/{department_id}",
        json={"name": "Renamed Department", "description": "A new description."},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["name"] == "Renamed Department"
    assert body["description"] == "A new description."

    fetched = client.get(f"/api/v1/departments/{department_id}").json()
    assert fetched["name"] == "Renamed Department"


def test_deleting_an_empty_department_succeeds(client, org_id):
    department_id = _create_department(client, org_id, name="Delete-me department")

    res = client.delete(f"/api/v1/departments/{department_id}")
    assert res.status_code == 204

    assert client.get(f"/api/v1/departments/{department_id}").status_code == 404


def test_deleting_a_missing_department_is_not_found(client):
    res = client.delete("/api/v1/departments/does-not-exist")
    assert res.status_code == 404


def test_deleting_a_department_with_employees_is_blocked(client, org_id):
    department_id = _create_department(client, org_id, name="Has-an-employee department")
    employee = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department_id,
            "full_name": "Department Delete Blocked Employee",
            "email": "department-delete-blocked@kowri.test",
        },
    )
    assert employee.status_code == 201, employee.text

    res = client.delete(f"/api/v1/departments/{department_id}")
    assert res.status_code == 409

    # Left fully intact — a blocked delete must not partially delete.
    assert client.get(f"/api/v1/departments/{department_id}").status_code == 200


def test_deleting_a_department_cascades_its_content_without_orphaning(client, org_id):
    department_id = _create_department(client, org_id, name="Fully-loaded department")

    role = client.post(
        "/api/v1/roles", json={"department_id": department_id, "title": "Test Role"}
    )
    assert role.status_code == 201, role.text
    role_id = role.json()["id"]

    project = client.post(
        "/api/v1/projects", json={"department_id": department_id, "name": "Test Project"}
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]

    team = client.post(
        f"/api/v1/departments/{department_id}/teams", json={"name": "Test Team"}
    )
    assert team.status_code == 201, team.text

    workspace = client.post(
        f"/api/v1/departments/{department_id}/workspace",
        json={
            "provider": "google_drive",
            "external_ref": "drive-ref-123",
            "display_name": "Shared Drive",
            "workspace_link": "https://drive.example.com/test",
        },
    )
    assert workspace.status_code == 201, workspace.text

    mission = client.post(
        "/api/v1/missions",
        json={
            "department_id": department_id,
            "project_id": project_id,
            "title": "Department Delete Test Mission",
            "mission_type": "task",
            "workspace_type": "reflection",
        },
    )
    assert mission.status_code == 201, mission.text
    mission_id = mission.json()["id"]

    quest = client.post(
        "/api/v1/quests",
        json={
            "department_id": department_id,
            "project_id": project_id,
            "title": "Department Delete Test Quest",
            "quest_type": "OTHER",
            "workspace_type": "GENERAL",
        },
    )
    assert quest.status_code == 201, quest.text
    quest_id = quest.json()["id"]

    dept_assignment = client.post(
        f"/api/v1/quests/{quest_id}/assignments",
        json={"assignment_type": "DEPARTMENT", "department_id": department_id},
    )
    assert dept_assignment.status_code == 201, dept_assignment.text

    role_assignment = client.post(
        f"/api/v1/quests/{quest_id}/assignments",
        json={"assignment_type": "ROLE", "role_id": role_id},
    )
    assert role_assignment.status_code == 201, role_assignment.text

    res = client.delete(f"/api/v1/departments/{department_id}")
    assert res.status_code == 204, res.text

    # The department itself, and the content it owns outright, are gone.
    assert client.get(f"/api/v1/departments/{department_id}").status_code == 404
    assert client.get(f"/api/v1/roles/{role_id}").status_code == 404
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 404

    # Mission/Quest content survives — only detached, per their FK's own
    # SET NULL semantics — never silently deleted along with the
    # department that happened to own it.
    surviving_mission = client.get(f"/api/v1/missions/{mission_id}").json()
    assert surviving_mission["department_id"] is None
    assert surviving_mission["project_id"] is None

    surviving_quest = client.get(f"/api/v1/quests/{quest_id}").json()
    assert surviving_quest["department_id"] is None
    assert surviving_quest["project_id"] is None

    # Both quest assignments targeted this now-gone department/role, so
    # neither means anything any more — both must be gone, not dangling.
    remaining_assignments = client.get(f"/api/v1/quests/{quest_id}/assignments").json()
    assert remaining_assignments == []

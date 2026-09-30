"""Tests for DELETE /missions/{mission_id} — added alongside the Manager
Portal's mission "Delete" action.

Runs against an isolated SQLite file, deleted and recreated each run
(same pattern as test_mission_attempts.py).
"""

import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_mission_delete.db"
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


@pytest.fixture(scope="module")
def department_id(client):
    return client.get("/api/v1/onboarding/bundle/demo").json()["employee"]["department_id"]


def _create_mission(client, department_id, *, title):
    res = client.post(
        "/api/v1/missions",
        json={
            "department_id": department_id,
            "title": title,
            "mission_type": "task",
            "workspace_type": "reflection",
            "required": False,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_deleting_an_unattempted_mission_succeeds(client, department_id):
    mission_id = _create_mission(client, department_id, title="Delete-me mission")

    res = client.delete(f"/api/v1/missions/{mission_id}")
    assert res.status_code == 204

    assert client.get(f"/api/v1/missions/{mission_id}").status_code == 404


def test_deleting_an_unattempted_mission_removes_its_assignments(client, org_id, department_id):
    mission_id = _create_mission(client, department_id, title="Assigned then deleted mission")
    employee = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department_id,
            "full_name": "Mission Delete Test Employee",
            "email": "mission-delete-test@kowri.test",
        },
    ).json()
    client.get(f"/api/v1/onboarding/bundle/{employee['id']}")  # provisions the assignment

    res = client.delete(f"/api/v1/missions/{mission_id}")
    assert res.status_code == 204

    # The employee's bundle (and its mission_assignments) must still load
    # cleanly — the deleted mission's assignment row shouldn't dangle.
    bundle = client.get(f"/api/v1/onboarding/bundle/{employee['id']}").json()
    assert all(a["mission_id"] != mission_id for a in bundle["mission_assignments"])


def test_deleting_a_missing_mission_is_not_found(client):
    res = client.delete("/api/v1/missions/does-not-exist")
    assert res.status_code == 404


def test_deleting_an_attempted_mission_is_blocked(client, org_id, department_id):
    mission_id = _create_mission(client, department_id, title="Attempted then delete-blocked mission")
    employee = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department_id,
            "full_name": "Mission Delete Blocked Employee",
            "email": "mission-delete-blocked@kowri.test",
        },
    ).json()
    client.get(f"/api/v1/onboarding/bundle/{employee['id']}")  # provisions the assignment

    attempt = client.post(
        "/api/v1/mission-attempts",
        json={"mission_id": mission_id, "employee_id": employee["id"]},
    ).json()
    submit = client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/submit",
        json={"employee_id": employee["id"], "reasoning": "Did it."},
    )
    assert submit.status_code == 200

    res = client.delete(f"/api/v1/missions/{mission_id}")
    assert res.status_code == 409

    # Left fully intact — a blocked delete must not partially delete.
    assert client.get(f"/api/v1/missions/{mission_id}").status_code == 200

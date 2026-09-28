"""Manager Portal employee actions: assigning an employee to a
department, and marking an employee inactive when they leave (with the
ability to reactivate them) — both exposed as manager-only PATCH
endpoints, gated behind the same admin session as the rest of the
Manager Portal.

Runs against its own isolated SQLite file, same convention as the
other test_*.py modules.
"""

import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_employee_management.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import itertools  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.config import get_settings  # noqa: E402

_email_counter = itertools.count()


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


@pytest.fixture(scope="module")
def department_a(client, org_id):
    return client.post(
        "/api/v1/departments", json={"organization_id": org_id, "name": "Employee Mgmt Dept A"}
    ).json()


@pytest.fixture(scope="module")
def department_b(client, org_id):
    return client.post(
        "/api/v1/departments", json={"organization_id": org_id, "name": "Employee Mgmt Dept B"}
    ).json()


@pytest.fixture
def employee(client, org_id, department_a):
    """A fresh employee per test so mutations in one test never leak
    into another."""
    return client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department_a["id"],
            "full_name": "Test Employee",
            "email": f"test-employee-{next(_email_counter)}@kowri.test",
        },
    ).json()


# =====================================================================
# Assigning an employee to a department
# =====================================================================


def test_assign_employee_to_department(client, employee, department_b):
    res = client.patch(
        f"/api/v1/employees/{employee['id']}/department",
        json={"department_id": department_b["id"]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["department_id"] == department_b["id"]

    # Persisted, not just echoed back.
    fetched = client.get(f"/api/v1/employees/{employee['id']}").json()
    assert fetched["department_id"] == department_b["id"]


def test_assign_employee_to_department_rejects_unknown_department(client, employee):
    res = client.patch(
        f"/api/v1/employees/{employee['id']}/department",
        json={"department_id": "not-a-real-department"},
    )
    assert res.status_code == 404


def test_assign_employee_department_rejects_unknown_employee(client, department_a):
    res = client.patch(
        "/api/v1/employees/not-a-real-employee/department",
        json={"department_id": department_a["id"]},
    )
    assert res.status_code == 404


def test_unassign_employee_department_with_null(client, employee):
    """A manager can also clear the department entirely (department_id: null)."""
    res = client.patch(f"/api/v1/employees/{employee['id']}/department", json={"department_id": None})
    assert res.status_code == 200, res.text
    assert res.json()["department_id"] is None


# =====================================================================
# Marking an employee inactive (and reactivating them)
# =====================================================================


def test_mark_employee_inactive(client, employee):
    res = client.patch(f"/api/v1/employees/{employee['id']}/status", json={"status": "inactive"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "inactive"

    fetched = client.get(f"/api/v1/employees/{employee['id']}").json()
    assert fetched["status"] == "inactive"


def test_reactivate_employee(client, employee):
    client.patch(f"/api/v1/employees/{employee['id']}/status", json={"status": "inactive"})
    res = client.patch(f"/api/v1/employees/{employee['id']}/status", json={"status": "active"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "active"


def test_inactive_employees_still_appear_in_the_full_list(client, employee):
    """Filtering active vs. inactive is a frontend list-view concern —
    the API itself must keep returning every employee regardless of
    status, so a manager can find someone to reactivate."""
    client.patch(f"/api/v1/employees/{employee['id']}/status", json={"status": "inactive"})
    all_employees = client.get("/api/v1/employees").json()
    assert any(e["id"] == employee["id"] for e in all_employees)


# =====================================================================
# Both actions require a manager session
# =====================================================================


def test_department_assignment_requires_login(employee, department_a):
    with TestClient(app) as anon:
        res = anon.patch(
            f"/api/v1/employees/{employee['id']}/department",
            json={"department_id": department_a["id"]},
        )
        assert res.status_code == 401


def test_status_update_requires_login(employee):
    with TestClient(app) as anon:
        res = anon.patch(f"/api/v1/employees/{employee['id']}/status", json={"status": "inactive"})
        assert res.status_code == 401

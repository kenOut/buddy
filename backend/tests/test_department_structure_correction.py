"""Correction — Complete Kowri Department Structure.

Covers the seed-data-only correction that completes the finalized
8-department org chart (Phase A left 3: Engineering, Products, Finance
— this adds the remaining 5: People & Culture, Sales, Marketing,
Compliance, Relation Management), and proves:

  - a fresh seeded database has exactly the 8 expected departments,
    exactly named
  - the new idempotent get-or-create helper (`_ensure_departments`)
    genuinely does not duplicate when called twice
  - Team distribution matches the current seed (Engineering 4 / Products
    2 / Finance 1 / everything else 0 — Engineering's roster was later
    replaced with the real Engineering Department Profile's four
    groupings, up from Phase A's original 3-team placeholder set)
  - existing Engineering/Products/Finance rows are not recreated
  - existing employee records (department_id, team, role_id, manager_id,
    supervisor_id) are completely untouched
  - `Employee` has no `team_id` attribute — Phase B was not implemented
  - the existing department API surfaces all 8 departments

Runs against its own isolated SQLite file, same convention as every
other test_*.py module. Uses the real `app.main.lifespan` function
(not a reimplementation) to seed, the same technique
test_production_seed_safety.py already established.
"""

import asyncio
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_department_structure_correction.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

import app.main as app_main  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models import Department, Employee, Team  # noqa: E402
from app.seed.seed_data import _ensure_departments  # noqa: E402

EXPECTED_DEPARTMENTS = {
    "Engineering",
    "Products",
    "Finance",
    "People & Culture",
    "Sales",
    "Marketing",
    "Compliance",
    "Relation Management",
}

EXPECTED_TEAM_COUNTS = {
    # Engineering — 4, not 3: the original TechOps/Security & IT/
    # Platform Engineering placeholder set was replaced with the real
    # Engineering Department Profile's four groupings (Leadership &
    # Delivery, Software Engineering & Platform, Technology Operations
    # (TechOps), Security & IT (SIT)).
    "Engineering": 4,
    "Products": 2,
    "Finance": 1,
    "People & Culture": 0,
    "Sales": 0,
    "Marketing": 0,
    "Compliance": 0,
    "Relation Management": 0,
}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def client():
    # Reassigned here, not just once at import time — this suite's own
    # established fragility class (first diagnosed in P2.1, recurring
    # in P3/P4.1): every test file sets DATABASE_URL once at module
    # top-level, but a module-scoped fixture doesn't actually execute
    # until pytest gets around to its first test, by which point a
    # later-collected file's own top-level assignment may have already
    # overwritten it. Reasserting immediately before TestClient(...)
    # triggers the real lifespan/seed guarantees this file runs against
    # its own isolated database regardless of collection order.
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"
    with TestClient(app_main.app) as c:
        c.post("/api/v1/admin/login", json={"password": get_settings().admin_password})
        yield c
    TEST_DB_PATH.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _restore_database_url_after_each_test():
    """Same discipline test_production_seed_safety.py already
    established: restore whatever DATABASE_URL was active before this
    file's tests ran, so as not to leave a stale value for any test
    collected after this file."""
    original = os.environ.get("DATABASE_URL")
    yield
    if original is not None:
        os.environ["DATABASE_URL"] = original


async def _department_names_and_ids() -> dict[str, str]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Department))
        return {d.name: d.id for d in result.scalars().all()}


async def _team_names_by_department(department_id: str) -> list[str]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Team).where(Team.department_id == department_id))
        return sorted(t.name for t in result.scalars().all())


# =====================================================================
# 1-2. Fresh seed has exactly the 8 expected departments, exactly named
# =====================================================================


def test_fresh_seed_contains_all_eight_required_departments(client):
    names_and_ids = run(_department_names_and_ids())
    assert EXPECTED_DEPARTMENTS.issubset(names_and_ids.keys())


def test_fresh_seed_total_is_exactly_eight(client):
    """The legacy "Design" department (predating the finalized 8-
    department org chart) has been removed from seed_data.py entirely,
    so a fresh seed now contains exactly the 8 required departments —
    no extra."""
    names_and_ids = run(_department_names_and_ids())
    assert set(names_and_ids.keys()) == EXPECTED_DEPARTMENTS
    assert len(names_and_ids) == 8


# =====================================================================
# 3. The idempotent helper does not duplicate when called twice
# =====================================================================


def test_ensure_departments_helper_is_idempotent(client):
    names_and_ids = run(_department_names_and_ids())
    org_id = None

    async def _org_id() -> str:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Department).where(Department.name == "Engineering"))
            return result.scalars().first().organization_id

    org_id = run(_org_id())

    payload = {
        "People & Culture": "Owns hiring, onboarding, and employee experience at Kowri.",
        "Sales": "Owns new business and revenue growth for Kowri's platform.",
        "Marketing": "Owns Kowri's brand, positioning, and go-to-market.",
        "Compliance": "Owns regulatory compliance across Kowri's markets.",
        "Relation Management": "Owns Kowri's key partner and merchant relationships.",
    }

    async def _call_twice():
        async with AsyncSessionLocal() as db:
            await _ensure_departments(db, org_id, payload)
            await db.commit()
        async with AsyncSessionLocal() as db:
            await _ensure_departments(db, org_id, payload)
            await db.commit()

    run(_call_twice())

    names_and_ids_after = run(_department_names_and_ids())
    assert len(names_and_ids_after) == len(names_and_ids), (
        "calling the helper twice must not duplicate any department"
    )
    # Every id is unchanged from before the two extra calls — proving
    # get-or-create found the existing rows rather than inserting new ones.
    for name in EXPECTED_DEPARTMENTS:
        assert names_and_ids_after[name] == names_and_ids[name]


def test_calling_seed_multiple_times_conceptually_does_not_duplicate(client):
    """First/second/third seed all report the same total — the literal
    shape your brief's Section 5 example describes ("first seed: N
    departments, second seed: still N, third seed: still N"), proven by
    calling the idempotent helper three times in a row against the same
    already-seeded database. The actual number is 8; what matters for
    this test is that it never grows."""

    async def _org_id() -> str:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Department).where(Department.name == "Engineering"))
            return result.scalars().first().organization_id

    org_id = run(_org_id())
    payload = {"People & Culture": "x", "Sales": "x", "Marketing": "x", "Compliance": "x", "Relation Management": "x"}

    counts = []
    for _ in range(3):
        async def _call():
            async with AsyncSessionLocal() as db:
                await _ensure_departments(db, org_id, payload)
                await db.commit()

        run(_call())
        counts.append(len(run(_department_names_and_ids())))

    assert counts == [counts[0]] * 3
    assert counts[0] == 8


# =====================================================================
# 4-11. Team distribution by department
# =====================================================================


@pytest.mark.parametrize("department_name", sorted(EXPECTED_TEAM_COUNTS))
def test_team_count_by_department(client, department_name):
    names_and_ids = run(_department_names_and_ids())
    teams = run(_team_names_by_department(names_and_ids[department_name]))
    assert len(teams) == EXPECTED_TEAM_COUNTS[department_name], (
        f"{department_name}: expected {EXPECTED_TEAM_COUNTS[department_name]} teams, got {teams}"
    )


def test_engineering_team_names_exact(client):
    names_and_ids = run(_department_names_and_ids())
    teams = run(_team_names_by_department(names_and_ids["Engineering"]))
    assert teams == sorted(
        [
            "Leadership & Delivery",
            "Software Engineering & Platform",
            "Technology Operations (TechOps)",
            "Security & IT (SIT)",
        ]
    )


def test_products_team_names_exact(client):
    names_and_ids = run(_department_names_and_ids())
    teams = run(_team_names_by_department(names_and_ids["Products"]))
    assert teams == sorted(["Delivery", "Customer Experience"])


def test_finance_team_names_exact(client):
    names_and_ids = run(_department_names_and_ids())
    teams = run(_team_names_by_department(names_and_ids["Finance"]))
    assert teams == ["FinOps"]


def test_total_team_count_is_seven(client):
    """7, not 6 — Engineering's roster grew from 3 to 4 teams when it
    was replaced with the real Engineering Department Profile's four
    groupings (Products' 2 + Finance's 1 + Engineering's 4 = 7)."""

    async def _total() -> int:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(func.count()).select_from(Team))
            return result.scalar_one()

    assert run(_total()) == 7


# =====================================================================
# 12. Existing Engineering/Products/Finance not duplicated
# =====================================================================


def test_engineering_products_finance_each_appear_exactly_once(client):
    async def _counts() -> dict[str, int]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Department.name))
            names = list(result.scalars().all())
        return {name: names.count(name) for name in ("Engineering", "Products", "Finance")}

    counts = run(_counts())
    assert counts == {"Engineering": 1, "Products": 1, "Finance": 1}


# =====================================================================
# 13. Existing employee records remain unchanged
# =====================================================================


def test_existing_employee_department_role_manager_supervisor_unchanged(client):
    """Updated for the later Engineering roster replacement (real
    Engineering Department Profile) — Nelikem Agbanu is now the demo
    identity (DEMO_EMPLOYEE_EMAIL), not Michael Mensah. This test's
    subject is "whatever the demo employee's own record says," which
    changed on purpose; the assertions below just pin down the new
    correct values rather than the old ones."""
    demo_bundle = client.get("/api/v1/onboarding/bundle/demo").json()
    employee = demo_bundle["employee"]
    assert employee["full_name"] == "Nelikem Agbanu"
    assert employee["job_title"] == "TechOps / Monitoring Engineer"
    assert employee["team"] == "Technology Operations (TechOps)"
    assert demo_bundle["department"]["name"] == "Engineering"
    assert demo_bundle["manager"]["full_name"] == "Kofi Asamoah"
    assert demo_bundle["supervisor"]["full_name"] == "Catherine Amarteifio"


def test_employee_count_after_roster_replacement(client):
    """17 — the original fictional/generated roster was removed from
    seed_data.py entirely (not just deactivated); only the real
    Engineering Department Profile roster (17) is seeded now."""

    async def _count() -> int:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(func.count()).select_from(Employee))
            return result.scalar_one()

    assert run(_count()) == 17


def test_no_fictional_legacy_employees_seeded(client):
    """The old placeholder roster (Sarah/David/Michael/teammates/
    generated FinOps+TechOps branch) is gone entirely — not deactivated,
    not present at all — now that seed_data.py no longer creates it."""

    async def _emails() -> set[str]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Employee.email))
            return set(result.scalars().all())

    emails = run(_emails())
    for legacy_email in ("michael.mensah@buddy.dev", "sarah.boateng@buddy.dev", "david.owusu@buddy.dev",
                          "ama.asante@buddy.dev", "kwame.adjei@buddy.dev"):
        assert legacy_email not in emails


# =====================================================================
# 14. Employee.team remains unchanged (still free text)
# =====================================================================


def test_employee_team_field_is_still_a_plain_string_column():
    from sqlalchemy import String

    column = Employee.__table__.columns["team"]
    assert isinstance(column.type, String)
    assert column.nullable is True


# =====================================================================
# 15. No Employee.team_id was introduced
# =====================================================================


def test_employee_has_no_team_id_column():
    assert "team_id" not in Employee.__table__.columns
    assert not hasattr(Employee, "team_id")


# =====================================================================
# 16. Existing department API returns all 8 departments
# =====================================================================


def test_department_api_returns_all_eight_required_departments(client):
    res = client.get("/api/v1/departments")
    assert res.status_code == 200
    names = {d["name"] for d in res.json()}
    assert EXPECTED_DEPARTMENTS.issubset(names)


def test_each_department_individually_retrievable(client):
    names_and_ids = run(_department_names_and_ids())
    for name, dept_id in names_and_ids.items():
        res = client.get(f"/api/v1/departments/{dept_id}")
        assert res.status_code == 200, f"{name} ({dept_id}) not retrievable"
        assert res.json()["name"] == name


def test_teams_endpoint_matches_expected_distribution_via_api(client):
    names_and_ids = run(_department_names_and_ids())
    for name, dept_id in names_and_ids.items():
        if name not in EXPECTED_TEAM_COUNTS:
            continue  # defensive: every department is expected to be in EXPECTED_TEAM_COUNTS now
        res = client.get(f"/api/v1/departments/{dept_id}/teams")
        assert res.status_code == 200
        assert len(res.json()) == EXPECTED_TEAM_COUNTS[name], f"{name}: {res.json()}"

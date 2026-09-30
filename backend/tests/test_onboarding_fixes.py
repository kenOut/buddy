"""Regression tests for the Phase 1 robustness fixes:

- GET /onboarding/bundle/* never writes and never duplicates mission
  assignments (fix #5).
- Employee PII can no longer be retrieved via an arbitrary email lookup
  (fix #6), replaced by a server-config-driven demo bootstrap.

Runs against an isolated SQLite file (deleted and recreated each run) so it
never touches the dev database.
"""

import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_buddy.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.config import get_settings  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Reassigned here, not just once at module import time — this
    # suite's own established fragility class (first diagnosed in
    # P2.1, recurring in P3/P4.1/the Correction phase): every test file
    # sets DATABASE_URL once at module top-level, but a module-scoped
    # fixture doesn't actually execute until pytest gets around to its
    # first test, by which point a later-collected file's own top-level
    # assignment may have already overwritten it. Reasserting
    # immediately before TestClient(...) triggers the real lifespan/
    # seed guarantees this file runs against its own isolated database
    # regardless of collection order.
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"
    with TestClient(app) as c:
        # Manager Portal auth (the login-gated admin/analytics/quest-builder
        # routers): authenticate this shared client once so every admin-only
        # call in this file works without each test managing its own session.
        c.post("/api/v1/admin/login", json={"password": get_settings().admin_password})

        # seed_data.py no longer seeds any demo Missions (see its own
        # module docstring) — this file's mission-assignment/reset tests
        # below need at least one real mission assigned to the demo
        # employee, so create it here, BEFORE that employee's first
        # bundle fetch. Mission assignments are only ever provisioned
        # once, at an employee's first bundle fetch (P2 — Provisioning
        # Boundary), so this must happen before any test calls
        # /onboarding/bundle/demo for the first time.
        employees = c.get("/api/v1/employees").json()
        demo_employee = next(e for e in employees if e["email"] == "nelikem.agbanu@buddy.dev")
        c.post(
            "/api/v1/missions",
            json={
                "department_id": demo_employee["department_id"],
                "title": "Meet your onboarding buddy",
                "mission_type": "task",
                "workspace_type": "reflection",
            },
        )

        yield c
    TEST_DB_PATH.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _restore_database_url_after_each_test():
    """Restore whatever DATABASE_URL was active before this file's
    tests ran, so as not to leave a stale value for any test collected
    after this file."""
    original = os.environ.get("DATABASE_URL")
    yield
    if original is not None:
        os.environ["DATABASE_URL"] = original


def test_demo_bundle_returns_seeded_employee(client):
    """Nelikem Agbanu, not Michael Mensah — DEMO_EMPLOYEE_EMAIL was
    updated when the real Engineering Department Profile roster
    replaced the original fictional demo roster."""
    res = client.get("/api/v1/onboarding/bundle/demo")
    assert res.status_code == 200
    assert res.json()["employee"]["email"] == "nelikem.agbanu@buddy.dev"


def test_repeated_bundle_reads_do_not_duplicate_mission_assignments(client):
    first = client.get("/api/v1/onboarding/bundle/demo")
    second = client.get("/api/v1/onboarding/bundle/demo")
    third = client.get("/api/v1/onboarding/bundle/demo")

    first_ids = sorted(a["id"] for a in first.json()["mission_assignments"])
    second_ids = sorted(a["id"] for a in second.json()["mission_assignments"])
    third_ids = sorted(a["id"] for a in third.json()["mission_assignments"])

    assert len(first_ids) > 0
    assert first_ids == second_ids == third_ids


def test_bundle_by_employee_id_is_also_read_only(client):
    demo = client.get("/api/v1/onboarding/bundle/demo").json()
    employee_id = demo["employee"]["id"]
    before = sorted(a["id"] for a in demo["mission_assignments"])

    res = client.get(f"/api/v1/onboarding/bundle/{employee_id}")
    after = sorted(a["id"] for a in res.json()["mission_assignments"])

    assert res.status_code == 200
    assert before == after


def test_employee_by_email_route_is_removed(client):
    res = client.get("/api/v1/employees/by-email/michael.mensah@buddy.dev")
    assert res.status_code == 404


def test_onboarding_bundle_by_email_route_is_removed(client):
    res = client.get("/api/v1/onboarding/bundle/by-email/michael.mensah@buddy.dev")
    assert res.status_code == 404


def test_session_scene_update_persists(client):
    demo = client.get("/api/v1/onboarding/bundle/demo").json()
    session_id = demo["session"]["id"]

    res = client.patch(
        f"/api/v1/onboarding/sessions/{session_id}", json={"current_scene": "department"}
    )
    assert res.status_code == 200
    assert res.json()["current_scene"] == "department"

    again = client.get("/api/v1/onboarding/bundle/demo").json()
    assert again["session"]["current_scene"] == "department"


# ---- POST /onboarding/demo/reset ----


def test_reset_puts_the_session_back_to_day_one(client):
    demo = client.get("/api/v1/onboarding/bundle/demo").json()
    session_id = demo["session"]["id"]
    client.patch(f"/api/v1/onboarding/sessions/{session_id}", json={"current_scene": "completion"})

    res = client.post("/api/v1/onboarding/demo/reset")
    assert res.status_code == 200
    session = res.json()["session"]
    assert session["current_scene"] == "welcome"
    assert session["status"] == "in_progress"
    assert session["progress_percent"] == 0
    assert session["completed_at"] is None

    again = client.get("/api/v1/onboarding/bundle/demo").json()
    assert again["session"]["current_scene"] == "welcome"


def test_reset_puts_a_completed_mission_back_to_pending(client):
    demo = client.get("/api/v1/onboarding/bundle/demo").json()
    employee_id = demo["employee"]["id"]
    simple = next(
        a for a in demo["mission_assignments"] if a["mission"]["title"] == "Meet your onboarding buddy"
    )
    attempt = client.post(
        "/api/v1/mission-attempts",
        json={"mission_id": simple["mission_id"], "employee_id": employee_id},
    ).json()
    completed = client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/submit",
        json={
            "employee_id": employee_id,
            "reasoning": "Talked through team norms and the on-call rotation with my buddy.",
        },
    )
    assert completed.json()["passed"] is True

    client.post("/api/v1/onboarding/demo/reset")

    again = client.get("/api/v1/onboarding/bundle/demo").json()
    reset_assignment = next(
        a for a in again["mission_assignments"] if a["mission"]["title"] == "Meet your onboarding buddy"
    )
    assert reset_assignment["status"] == "pending"
    assert reset_assignment["completed_at"] is None


def test_reset_clears_quest_attempts_so_readiness_recomputes(client):
    demo = client.get("/api/v1/onboarding/bundle/demo").json()
    employee_id = demo["employee"]["id"]

    quest = client.post(
        "/api/v1/quests",
        json={
            "department_id": demo["department"]["id"],
            "title": "Reset regression quest",
            "description": "A real challenge description.",
            "quest_type": "INVESTIGATE",
            "workspace_type": "INVESTIGATION",
            "difficulty": "MEDIUM",
        },
    ).json()
    quest_id = quest["id"]
    client.post(
        f"/api/v1/quests/{quest_id}/tasks",
        json={"title": "Investigate it", "task_type": "INVESTIGATE", "sort_order": 0, "required": False},
    )
    client.post(f"/api/v1/quests/{quest_id}/evidence", json={"title": "E", "evidence_type": "METRICS", "content": {}})
    client.post(
        f"/api/v1/quests/{quest_id}/evaluation-criteria",
        json={"name": "C", "criterion_type": "DETERMINISTIC", "expected_answer": "x", "max_score": 100},
    )
    capability_id = client.get("/api/v1/capabilities").json()[0]["id"]
    client.post(
        f"/api/v1/quests/{quest_id}/capabilities",
        json={"capability_id": capability_id, "weight": 1.0},
    )
    client.post(
        f"/api/v1/quests/{quest_id}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee_id},
    )
    published = client.post(f"/api/v1/quests/{quest_id}/publish")
    assert published.status_code == 200, published.text

    attempt_res = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest_id, "employee_id": employee_id}
    )
    assert attempt_res.status_code == 201, attempt_res.text
    attempt = attempt_res.json()
    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": employee_id, "reasoning": "It's x."},
    )
    submitted = client.post(
        f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": employee_id}
    )
    assert submitted.status_code == 200
    client.post(f"/api/v1/quest-attempts/{attempt['id']}/evaluate", json={"employee_id": employee_id})

    before = client.get(f"/api/v1/quest-attempts/{attempt['id']}?employee_id={employee_id}")
    assert before.status_code == 200

    client.post("/api/v1/onboarding/demo/reset")

    after = client.get(f"/api/v1/quest-attempts/{attempt['id']}?employee_id={employee_id}")
    assert after.status_code == 404  # attempt row is gone, not just reset in place


def test_reset_does_not_require_an_admin_session(client):
    # Drop the shared client's admin cookie for one call — proves a real
    # employee (no admin session) can reach this, since it's meant to be
    # triggered from the employee-facing Completion scene.
    saved_cookie = client.cookies.get("buddy_admin_session")
    del client.cookies["buddy_admin_session"]
    try:
        res = client.post("/api/v1/onboarding/demo/reset")
    finally:
        client.cookies.set("buddy_admin_session", saved_cookie)
    assert res.status_code == 200

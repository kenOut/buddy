"""Phase 3B Stage 1 backend tests: Quest + QuestAttempt core.

Runs against an isolated SQLite file (separate from the other test
modules' DBs), deleted and recreated each run — same convention as
test_mission_attempts.py.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_quests.db"
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


@pytest.fixture(scope="module")
def demo_employee_id(client):
    bundle = client.get("/api/v1/onboarding/bundle/demo").json()
    return bundle["employee"]["id"]


@pytest.fixture(scope="module")
def demo_department_id(client):
    bundle = client.get("/api/v1/onboarding/bundle/demo").json()
    return bundle["employee"]["department_id"]


@pytest.fixture(scope="module")
def demo_project_id(client, demo_department_id):
    # seed_data.py no longer seeds any demo Projects (they existed only
    # as project_id FKs for the demo Missions removed alongside them —
    # see seed_data.py's own module docstring), so this file creates its
    # own instead of assuming one already exists.
    res = client.post(
        "/api/v1/projects",
        json={
            "department_id": demo_department_id,
            "name": "Quest Test Project",
            "description": "A project used only for these Quest tests.",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _quest_payload(**overrides):
    payload = {
        "title": "Diagnose a checkout latency spike in a new region",
        "description": "A fresh investigation challenge for a different environment.",
        "quest_type": "INVESTIGATE",
        "workspace_type": "INVESTIGATION",
    }
    payload.update(overrides)
    return payload


def _publish_for_employee(client, quest_id, employee_id):
    """Stage 3: a quest must be PUBLISHED with a matching active
    assignment before any attempt can be created against it. Shared by
    every attempt-creation test below, since that's now a precondition,
    not just a nice-to-have. Stage 6A additionally requires at least one
    mapped capability before publish is allowed. Phase 6B additionally
    requires, for an INVESTIGATE quest (this file's default quest_type),
    at least one INVESTIGATE-typed task, at least one evidence item, and
    a well-formed evaluation criterion — see quest_quality_service."""
    task_res = client.post(
        f"/api/v1/quests/{quest_id}/tasks",
        json={"title": "Identify the affected service", "task_type": "INVESTIGATE"},
    )
    assert task_res.status_code == 201, task_res.text
    evidence_res = client.post(
        f"/api/v1/quests/{quest_id}/evidence",
        json={"title": "Latency metrics", "evidence_type": "METRICS", "content": {"note": "spiked"}},
    )
    assert evidence_res.status_code == 201, evidence_res.text
    criterion_res = client.post(
        f"/api/v1/quests/{quest_id}/evaluation-criteria",
        json={
            "name": "Identifies the affected service",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "checkout-service",
        },
    )
    assert criterion_res.status_code == 201, criterion_res.text
    caps = client.get("/api/v1/capabilities").json()
    cap_res = client.post(
        f"/api/v1/quests/{quest_id}/capabilities", json={"capability_id": caps[0]["id"]}
    )
    assert cap_res.status_code in (201, 409), cap_res.text  # 409 if already mapped by a prior call
    assign_res = client.post(
        f"/api/v1/quests/{quest_id}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee_id},
    )
    assert assign_res.status_code == 201, assign_res.text
    publish_res = client.post(f"/api/v1/quests/{quest_id}/publish")
    assert publish_res.status_code == 200, publish_res.text
    return publish_res.json()


# ---- quest creation ----


def test_create_quest_returns_201_with_draft_status(client, demo_project_id, demo_department_id, demo_employee_id):
    res = client.post(
        "/api/v1/quests",
        json=_quest_payload(
            project_id=demo_project_id,
            department_id=demo_department_id,
            created_by_employee_id=demo_employee_id,
        ),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "DRAFT"
    assert body["quest_type"] == "INVESTIGATE"
    assert body["workspace_type"] == "INVESTIGATION"
    assert body["difficulty"] == "MEDIUM"
    assert body["project_id"] == demo_project_id


def test_create_quest_without_project_or_department_is_allowed(client):
    res = client.post("/api/v1/quests", json=_quest_payload(title="A quest with no project yet"))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["project_id"] is None
    assert body["department_id"] is None
    assert body["created_by_employee_id"] is None


def test_create_quest_rejects_unknown_quest_type(client):
    res = client.post("/api/v1/quests", json=_quest_payload(quest_type="NOT_A_REAL_TYPE"))
    assert res.status_code == 422


def test_create_quest_rejects_unknown_workspace_type(client):
    res = client.post("/api/v1/quests", json=_quest_payload(workspace_type="NOT_A_REAL_WORKSPACE"))
    assert res.status_code == 422


def test_create_quest_rejects_unknown_difficulty(client):
    res = client.post("/api/v1/quests", json=_quest_payload(difficulty="IMPOSSIBLE"))
    assert res.status_code == 422


# ---- quest retrieval ----


def test_get_existing_quest_returns_200(client):
    created = client.post("/api/v1/quests", json=_quest_payload(title="Fetch me back")).json()
    res = client.get(f"/api/v1/quests/{created['id']}")
    assert res.status_code == 200
    assert res.json()["id"] == created["id"]


def test_get_unknown_quest_returns_404(client):
    res = client.get("/api/v1/quests/does-not-exist")
    assert res.status_code == 404


# ---- quest listing ----


def test_list_quests_includes_created_quest(client):
    created = client.post("/api/v1/quests", json=_quest_payload(title="Show up in the list")).json()
    res = client.get("/api/v1/quests")
    assert res.status_code == 200
    ids = [q["id"] for q in res.json()]
    assert created["id"] in ids


# ---- quest update ----


def test_update_quest_fields_persist(client):
    created = client.post("/api/v1/quests", json=_quest_payload(title="Original title")).json()
    res = client.patch(
        f"/api/v1/quests/{created['id']}",
        json={"title": "Updated title", "difficulty": "HARD"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["title"] == "Updated title"
    assert body["difficulty"] == "HARD"
    # untouched fields survive a partial update
    assert body["quest_type"] == "INVESTIGATE"
    assert body["status"] == "DRAFT"

    refetched = client.get(f"/api/v1/quests/{created['id']}").json()
    assert refetched["title"] == "Updated title"


def test_update_unknown_quest_returns_404(client):
    res = client.patch("/api/v1/quests/does-not-exist", json={"title": "x"})
    assert res.status_code == 404


def test_patch_status_field_is_silently_ignored(client):
    """Stage 3: publishing/archiving must go through their own dedicated
    endpoints, never an ordinary PATCH — QuestUpdate no longer has a
    `status` field at all, so a `status` key in the body has no effect."""
    created = client.post("/api/v1/quests", json=_quest_payload(title="Cannot PATCH status")).json()
    assert created["status"] == "DRAFT"
    res = client.patch(f"/api/v1/quests/{created['id']}", json={"status": "PUBLISHED"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "DRAFT"


# ---- quest attempt creation ----


def test_create_quest_attempt(client, demo_employee_id):
    quest = client.post("/api/v1/quests", json=_quest_payload(title="Attempt this one")).json()
    _publish_for_employee(client, quest["id"], demo_employee_id)
    res = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest["id"], "employee_id": demo_employee_id}
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["quest_id"] == quest["id"]
    assert body["employee_id"] == demo_employee_id
    assert body["status"] == "NOT_STARTED"
    assert body["submission"] == {}


def test_create_quest_attempt_for_unknown_quest_returns_404(client, demo_employee_id):
    res = client.post(
        "/api/v1/quest-attempts", json={"quest_id": "does-not-exist", "employee_id": demo_employee_id}
    )
    assert res.status_code == 404


def test_create_quest_attempt_for_unknown_employee_returns_404(client):
    quest = client.post("/api/v1/quests", json=_quest_payload(title="No such employee")).json()
    res = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest["id"], "employee_id": "does-not-exist"}
    )
    assert res.status_code == 404


def test_create_quest_attempt_rejected_for_draft_quest(client, demo_employee_id):
    quest = client.post("/api/v1/quests", json=_quest_payload(title="Still a draft")).json()
    res = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest["id"], "employee_id": demo_employee_id}
    )
    assert res.status_code == 409, res.text


# ---- attempt idempotency ----


def test_repeated_sequential_attempt_creation_returns_same_row(client, demo_employee_id):
    quest = client.post("/api/v1/quests", json=_quest_payload(title="Idempotent sequential")).json()
    _publish_for_employee(client, quest["id"], demo_employee_id)
    payload = {"quest_id": quest["id"], "employee_id": demo_employee_id}

    first = client.post("/api/v1/quest-attempts", json=payload).json()
    second = client.post("/api/v1/quest-attempts", json=payload).json()
    third = client.post("/api/v1/quest-attempts", json=payload).json()

    assert first["id"] == second["id"] == third["id"]

    all_attempts = client.get("/api/v1/quests").json()  # sanity: listing still works
    assert all_attempts  # not empty


def test_concurrent_attempt_creation_produces_exactly_one_row(client, demo_employee_id):
    quest = client.post("/api/v1/quests", json=_quest_payload(title="Idempotent concurrent")).json()
    _publish_for_employee(client, quest["id"], demo_employee_id)
    payload = {"quest_id": quest["id"], "employee_id": demo_employee_id}

    def create():
        return client.post("/api/v1/quest-attempts", json=payload)

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: create(), range(8)))

    for res in responses:
        assert res.status_code == 201, res.text

    attempt_ids = {res.json()["id"] for res in responses}
    assert len(attempt_ids) == 1, f"expected exactly one attempt id, got {attempt_ids}"

    # Verify at the database level too, not just via the API responses.
    async def count_rows():
        from sqlalchemy import func, select

        from app.db.session import AsyncSessionLocal
        from app.models import QuestAttempt

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(func.count()).select_from(QuestAttempt).where(
                    QuestAttempt.quest_id == quest["id"],
                    QuestAttempt.employee_id == demo_employee_id,
                )
            )
            return result.scalar_one()

    import asyncio

    row_count = asyncio.run(count_rows())
    assert row_count == 1, f"expected exactly 1 QuestAttempt row in the database, found {row_count}"


# ---- attempt retrieval ----


def test_get_existing_attempt_returns_200(client, demo_employee_id):
    quest = client.post("/api/v1/quests", json=_quest_payload(title="Fetch attempt back")).json()
    _publish_for_employee(client, quest["id"], demo_employee_id)
    created = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest["id"], "employee_id": demo_employee_id}
    ).json()

    res = client.get(f"/api/v1/quest-attempts/{created['id']}", params={"employee_id": demo_employee_id})
    assert res.status_code == 200
    assert res.json()["id"] == created["id"]


def test_get_unknown_attempt_returns_404(client, demo_employee_id):
    res = client.get("/api/v1/quest-attempts/does-not-exist", params={"employee_id": demo_employee_id})
    assert res.status_code == 404

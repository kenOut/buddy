"""Phase 3B Stage 6A backend tests: Manager Quest Builder foundation —
publish readiness validation and published-quest immutability.

Runs against an isolated SQLite file, deleted and recreated each run —
same convention as the other test_quest_*.py modules.
"""

import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_quest_builder.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.config import get_settings  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        # Manager Portal auth (the login-gated admin/analytics/quest-builder
        # routers): authenticate this shared client once so every admin-only
        # call in this file works without each test managing its own session.
        c.post("/api/v1/admin/login", json={"password": get_settings().admin_password})
        yield c
    TEST_DB_PATH.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def demo_employee_id(client):
    bundle = client.get("/api/v1/onboarding/bundle/demo").json()
    return bundle["employee"]["id"]


@pytest.fixture(scope="module")
def capability_ids(client):
    caps = client.get("/api/v1/capabilities").json()
    return {c["key"]: c["id"] for c in caps}


def _new_quest(client, **overrides):
    payload = {
        "title": "Builder test quest",
        "quest_type": "INVESTIGATE",
        "workspace_type": "INVESTIGATION",
    }
    payload.update(overrides)
    return client.post("/api/v1/quests", json=payload).json()


def _make_publishable(client, quest_id, employee_id, capability_ids, *, description=True):
    """Phase 6B: publishing an INVESTIGATE quest (this file's default
    quest_type) also requires an INVESTIGATE-typed task, an evidence
    item, and a well-formed evaluation criterion — see
    quest_quality_service. See tests/test_quest_quality.py for dedicated,
    type-aware Phase 6B coverage; this file stays focused on the Stage 6A
    authoring/immutability/security behaviors it was written for."""
    if description:
        client.patch(f"/api/v1/quests/{quest_id}", json={"description": "A real workplace problem."})
    client.post(
        f"/api/v1/quests/{quest_id}/tasks",
        json={"title": "Identify the affected service", "task_type": "INVESTIGATE", "required": False},
    )
    client.post(
        f"/api/v1/quests/{quest_id}/evidence",
        json={"title": "Latency metrics", "evidence_type": "METRICS", "content": {}},
    )
    client.post(
        f"/api/v1/quests/{quest_id}/evaluation-criteria",
        json={
            "name": "Identifies the affected service",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "checkout-service",
        },
    )
    client.post(
        f"/api/v1/quests/{quest_id}/capabilities",
        json={"capability_id": capability_ids["troubleshooting"]},
    )
    client.post(
        f"/api/v1/quests/{quest_id}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee_id},
    )


# =====================================================================
# Quest creation / draft editing
# =====================================================================


def test_create_draft_quest(client):
    res = client.post(
        "/api/v1/quests",
        json={"title": "A brand new draft", "quest_type": "BUILD", "workspace_type": "BUILD"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "DRAFT"


def test_update_draft_quest(client):
    quest = _new_quest(client, title="Editable while draft")
    res = client.patch(f"/api/v1/quests/{quest['id']}", json={"title": "Edited title"})
    assert res.status_code == 200, res.text
    assert res.json()["title"] == "Edited title"


def test_invalid_quest_type_rejected(client):
    res = client.post(
        "/api/v1/quests",
        json={"title": "Bad type", "quest_type": "NOT_REAL", "workspace_type": "GENERAL"},
    )
    assert res.status_code == 422


# =====================================================================
# Publish readiness endpoint
# =====================================================================


def test_publish_readiness_shows_missing_requirements(client):
    """Phase 6B: the endpoint now returns structured Quest Quality
    Validation (code/severity/message/section/satisfied), not the old
    Stage 6A key/label/blocking shape. See test_quest_quality.py for the
    full type-aware validation matrix."""
    quest = _new_quest(client, title="Nothing configured yet")
    res = client.get(f"/api/v1/quests/{quest['id']}/publish-readiness")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ready"] is False
    codes = {c["code"]: c for c in body["checks"]}
    assert codes["MISSING_CHALLENGE"]["satisfied"] is False
    assert codes["MISSING_CAPABILITY"]["satisfied"] is False
    assert codes["MISSING_ASSIGNMENT"]["satisfied"] is False
    assert {e["code"] for e in body["errors"]} >= {
        "MISSING_CHALLENGE",
        "MISSING_CAPABILITY",
        "MISSING_ASSIGNMENT",
    }


def test_publish_readiness_shows_ready_once_complete(client, demo_employee_id, capability_ids):
    quest = _new_quest(client, title="Fully configured")
    _make_publishable(client, quest["id"], demo_employee_id, capability_ids)
    res = client.get(f"/api/v1/quests/{quest['id']}/publish-readiness").json()
    assert res["ready"] is True
    assert res["errors"] == []


# =====================================================================
# Publish validation (backend-authoritative)
# =====================================================================


def test_publish_rejected_with_no_challenge(client, demo_employee_id, capability_ids):
    quest = _new_quest(client, title="No challenge")
    client.post(
        f"/api/v1/quests/{quest['id']}/capabilities",
        json={"capability_id": capability_ids["troubleshooting"]},
    )
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    res = client.post(f"/api/v1/quests/{quest['id']}/publish")
    assert res.status_code == 409, res.text
    assert "challenge" in res.json()["detail"].lower()


def test_publish_rejected_with_no_capability(client, demo_employee_id):
    quest = _new_quest(client, title="No capability")
    client.patch(f"/api/v1/quests/{quest['id']}", json={"description": "A real problem."})
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": demo_employee_id},
    )
    res = client.post(f"/api/v1/quests/{quest['id']}/publish")
    assert res.status_code == 409, res.text
    assert "capabilit" in res.json()["detail"].lower()


def test_publish_rejected_with_no_assignment(client, capability_ids):
    quest = _new_quest(client, title="No assignment")
    client.patch(f"/api/v1/quests/{quest['id']}", json={"description": "A real problem."})
    client.post(
        f"/api/v1/quests/{quest['id']}/capabilities",
        json={"capability_id": capability_ids["troubleshooting"]},
    )
    res = client.post(f"/api/v1/quests/{quest['id']}/publish")
    assert res.status_code == 409, res.text
    assert "assignment" in res.json()["detail"].lower()


def test_publish_rejected_lists_all_missing_requirements_at_once(client):
    quest = _new_quest(client, title="Missing everything")
    res = client.post(f"/api/v1/quests/{quest['id']}/publish")
    assert res.status_code == 409
    detail = res.json()["detail"].lower()
    assert "challenge" in detail
    assert "capabilit" in detail
    assert "assignment" in detail


def test_valid_quest_publishes(client, demo_employee_id, capability_ids):
    quest = _new_quest(client, title="Everything configured")
    _make_publishable(client, quest["id"], demo_employee_id, capability_ids)
    res = client.post(f"/api/v1/quests/{quest['id']}/publish")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "PUBLISHED"


# =====================================================================
# Published Quest immutability
# =====================================================================


def test_published_quest_basic_info_cannot_be_mutated(client, demo_employee_id, capability_ids):
    quest = _new_quest(client, title="Immutable once published")
    _make_publishable(client, quest["id"], demo_employee_id, capability_ids)
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.patch(f"/api/v1/quests/{quest['id']}", json={"title": "Sneaky edit"})
    assert res.status_code == 409, res.text

    unchanged = client.get(f"/api/v1/quests/{quest['id']}").json()
    assert unchanged["title"] == "Immutable once published"


def test_published_quest_cannot_add_task(client, demo_employee_id, capability_ids):
    quest = _new_quest(client, title="No new tasks after publish")
    _make_publishable(client, quest["id"], demo_employee_id, capability_ids)
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.post(
        f"/api/v1/quests/{quest['id']}/tasks",
        json={"title": "Sneaky task", "task_type": "OTHER"},
    )
    assert res.status_code == 409, res.text


def test_published_quest_cannot_edit_existing_task(client, demo_employee_id, capability_ids):
    quest = _new_quest(client, title="No task edits after publish")
    task = client.post(
        f"/api/v1/quests/{quest['id']}/tasks", json={"title": "Original", "task_type": "OTHER"}
    ).json()
    _make_publishable(client, quest["id"], demo_employee_id, capability_ids)
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.patch(
        f"/api/v1/quests/{quest['id']}/tasks/{task['id']}", json={"title": "Sneaky edit"}
    )
    assert res.status_code == 409, res.text


def test_published_quest_cannot_delete_task(client, demo_employee_id, capability_ids):
    quest = _new_quest(client, title="No task deletion after publish")
    task = client.post(
        f"/api/v1/quests/{quest['id']}/tasks", json={"title": "Keep me", "task_type": "OTHER"}
    ).json()
    _make_publishable(client, quest["id"], demo_employee_id, capability_ids)
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.delete(f"/api/v1/quests/{quest['id']}/tasks/{task['id']}")
    assert res.status_code == 409, res.text

    still_there = client.get(f"/api/v1/quests/{quest['id']}/tasks").json()
    assert any(t["id"] == task["id"] for t in still_there)


def test_published_quest_cannot_add_evidence(client, demo_employee_id, capability_ids):
    quest = _new_quest(client, title="No new evidence after publish")
    _make_publishable(client, quest["id"], demo_employee_id, capability_ids)
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.post(
        f"/api/v1/quests/{quest['id']}/evidence", json={"title": "Sneaky evidence", "evidence_type": "TEXT"}
    )
    assert res.status_code == 409, res.text


def test_published_quest_cannot_add_criterion(client, demo_employee_id, capability_ids):
    quest = _new_quest(client, title="No new criteria after publish")
    _make_publishable(client, quest["id"], demo_employee_id, capability_ids)
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.post(
        f"/api/v1/quests/{quest['id']}/evaluation-criteria",
        json={"name": "Sneaky criterion", "criterion_type": "QUALITATIVE"},
    )
    assert res.status_code == 409, res.text


def test_published_quest_cannot_add_capability_mapping(client, demo_employee_id, capability_ids):
    quest = _new_quest(client, title="No new capabilities after publish")
    _make_publishable(client, quest["id"], demo_employee_id, capability_ids)
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.post(
        f"/api/v1/quests/{quest['id']}/capabilities",
        json={"capability_id": capability_ids["documentation"]},
    )
    assert res.status_code == 409, res.text


def test_published_quest_cannot_remove_capability_mapping(client, demo_employee_id, capability_ids):
    quest = _new_quest(client, title="No capability removal after publish")
    _make_publishable(client, quest["id"], demo_employee_id, capability_ids)
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.delete(
        f"/api/v1/quests/{quest['id']}/capabilities/{capability_ids['troubleshooting']}"
    )
    assert res.status_code == 409, res.text


def test_archived_quest_content_also_remains_immutable(client, demo_employee_id, capability_ids):
    quest = _new_quest(client, title="Archived stays immutable")
    _make_publishable(client, quest["id"], demo_employee_id, capability_ids)
    client.post(f"/api/v1/quests/{quest['id']}/publish")
    client.post(f"/api/v1/quests/{quest['id']}/archive")

    res = client.patch(f"/api/v1/quests/{quest['id']}", json={"title": "Sneaky archived edit"})
    assert res.status_code == 409, res.text


def test_assignments_remain_mutable_after_publish(client, demo_employee_id, capability_ids, client_other_employee=None):
    """The one deliberate exception to immutability (Stage 6A §23) — who
    a quest is assigned to must stay changeable regardless of status."""
    quest = _new_quest(client, title="Assignments stay mutable after publish")
    _make_publishable(client, quest["id"], demo_employee_id, capability_ids)
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    org_id = client.get("/api/v1/onboarding/bundle/demo").json()["employee"]["organization_id"]
    dept_id = client.get("/api/v1/onboarding/bundle/demo").json()["employee"]["department_id"]
    new_employee = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": dept_id,
            "full_name": "Newly Assigned",
            "email": "newly-assigned@buddy.dev",
            "start_date": "2026-01-01",
        },
    ).json()

    res = client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": new_employee["id"]},
    )
    assert res.status_code == 201, res.text


# =====================================================================
# Content CRUD (draft state) — create/update/delete for each child type
# =====================================================================


def test_task_crud_on_draft_quest(client):
    quest = _new_quest(client, title="Task CRUD")
    created = client.post(
        f"/api/v1/quests/{quest['id']}/tasks", json={"title": "Step 1", "task_type": "INVESTIGATE"}
    )
    assert created.status_code == 201
    task_id = created.json()["id"]

    updated = client.patch(f"/api/v1/quests/{quest['id']}/tasks/{task_id}", json={"title": "Step 1 revised"})
    assert updated.status_code == 200
    assert updated.json()["title"] == "Step 1 revised"

    deleted = client.delete(f"/api/v1/quests/{quest['id']}/tasks/{task_id}")
    assert deleted.status_code == 204


def test_evidence_crud_on_draft_quest(client):
    quest = _new_quest(client, title="Evidence CRUD")
    created = client.post(
        f"/api/v1/quests/{quest['id']}/evidence",
        json={"title": "Server logs", "evidence_type": "LOGS", "content": {"detail": "..."}},
    )
    assert created.status_code == 201
    evidence_id = created.json()["id"]

    updated = client.patch(
        f"/api/v1/quests/{quest['id']}/evidence/{evidence_id}", json={"title": "Server logs (revised)"}
    )
    assert updated.status_code == 200

    deleted = client.delete(f"/api/v1/quests/{quest['id']}/evidence/{evidence_id}")
    assert deleted.status_code == 204


def test_criterion_crud_on_draft_quest(client):
    quest = _new_quest(client, title="Criterion CRUD")
    created = client.post(
        f"/api/v1/quests/{quest['id']}/evaluation-criteria",
        json={"name": "Correctness", "criterion_type": "DETERMINISTIC", "expected_answer": "checkout-service"},
    )
    assert created.status_code == 201
    criterion_id = created.json()["id"]

    updated = client.patch(
        f"/api/v1/quests/{quest['id']}/evaluation-criteria/{criterion_id}", json={"max_score": 75}
    )
    assert updated.status_code == 200
    assert updated.json()["max_score"] == 75

    deleted = client.delete(f"/api/v1/quests/{quest['id']}/evaluation-criteria/{criterion_id}")
    assert deleted.status_code == 204


def test_capability_mapping_crud_on_draft_quest(client, capability_ids):
    quest = _new_quest(client, title="Capability CRUD")
    created = client.post(
        f"/api/v1/quests/{quest['id']}/capabilities",
        json={"capability_id": capability_ids["communication"]},
    )
    assert created.status_code == 201

    deleted = client.delete(
        f"/api/v1/quests/{quest['id']}/capabilities/{capability_ids['communication']}"
    )
    assert deleted.status_code == 204


# =====================================================================
# Security: manager/internal schemas stay separate from employee-safe ones
# =====================================================================


def test_employee_response_unchanged_by_builder_additions(client, demo_employee_id, capability_ids):
    """Confirms Stage 6A's new checks don't accidentally widen what the
    employee-safe route returns."""
    quest = _new_quest(client, title="Employee response still safe")
    client.post(
        f"/api/v1/quests/{quest['id']}/evaluation-criteria",
        json={
            "name": "hidden",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "SECRET_BUILDER_STAGE_LEAK_CHECK",
        },
    )
    _make_publishable(client, quest["id"], demo_employee_id, capability_ids)
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    res = client.get(f"/api/v1/quests/{quest['id']}/employee", params={"employee_id": demo_employee_id})
    assert res.status_code == 200, res.text
    assert "SECRET_BUILDER_STAGE_LEAK_CHECK" not in res.text
    assert "evaluation_criteria" not in res.text


def test_manager_detail_response_contains_hidden_fields_for_authoring(client, demo_employee_id, capability_ids):
    """The manager/internal schema (QuestDetailResponse) is deliberately
    the ONE place hidden fields are readable — that's what makes it a
    genuine authoring surface, not a duplicate of the employee schema."""
    quest = _new_quest(client, title="Manager detail has hidden fields")
    client.post(
        f"/api/v1/quests/{quest['id']}/evaluation-criteria",
        json={
            "name": "visible-to-manager",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "MANAGER_VISIBLE_ANSWER",
        },
    )
    res = client.get(f"/api/v1/quests/{quest['id']}/detail")
    assert res.status_code == 200
    assert "MANAGER_VISIBLE_ANSWER" in res.text


# =====================================================================
# Regression
# =====================================================================


def test_existing_quest_evaluation_flow_still_works(client, demo_employee_id, capability_ids):
    quest = _new_quest(client, title="Evaluation regression check")
    _make_publishable(client, quest["id"], demo_employee_id, capability_ids)
    client.post(f"/api/v1/quests/{quest['id']}/publish")

    attempt = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest["id"], "employee_id": demo_employee_id}
    ).json()
    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "solution": "a reasonable solution"},
    )
    submit = client.post(
        f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": demo_employee_id}
    )
    assert submit.status_code == 200

    evaluate = client.post(
        f"/api/v1/quest-attempts/{attempt['id']}/evaluate", json={"employee_id": demo_employee_id}
    )
    assert evaluate.status_code == 200
    assert evaluate.json()["status"] == "COMPLETED"


def test_mission_flow_still_works(client):
    bundle = client.get("/api/v1/onboarding/bundle/demo").json()
    res = client.get(f"/api/v1/employees/{bundle['employee']['id']}/missions")
    assert res.status_code == 200

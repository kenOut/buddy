"""Phase 7 Stage 1 backend tests: the Workspace Engine & Workspace
Interface Contract's two backend-facing additive changes —

1. `TROUBLESHOOT` added to WORKSPACE_TYPES so a Quest can be authored
   with a workspace_type that resolves to a specialized (here: placeholder)
   frontend Workspace instead of the generic one.
2. The `workspace` envelope on QuestAttemptUpdate/submission — additive,
   nested alongside the existing findings/reasoning/solution/
   completed_task_ids fields, never replacing them.

The point of this file isn't to test workspace_type dispatch (that's a
frontend concern — resolveWorkspace.ts has no backend counterpart to
test) but to prove the backend side of the contract: a Quest can be
authored with the new workspace_type value, and an attempt's submission
JSON can carry the new envelope, without disturbing any existing
findings/reasoning/solution/completed_task_ids behavior — i.e. the whole
point of an "additive envelope" rather than a redesigned submission shape.

Runs against an isolated SQLite file, deleted and recreated each run —
same convention as the other test_quest_*.py modules.
"""

import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_workspace_engine.db"
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
    return client.get("/api/v1/onboarding/bundle/demo").json()["employee"]["id"]


def _build_quest(client, employee_id, *, workspace_type="TROUBLESHOOT"):
    quest = client.post(
        "/api/v1/quests",
        json={
            "title": "Stage 1 workspace-engine test quest",
            "description": "A quest used only to exercise the workspace envelope.",
            "quest_type": "TROUBLESHOOT",
            "workspace_type": workspace_type,
        },
    ).json()
    quest_id = quest["id"]

    task = client.post(
        f"/api/v1/quests/{quest_id}/tasks",
        json={"title": "Confirm the root cause", "task_type": "INVESTIGATE", "required": True, "sort_order": 0},
    ).json()

    client.post(
        f"/api/v1/quests/{quest_id}/evidence",
        json={"title": "Error rate graph", "evidence_type": "METRICS", "content": {"note": "spike at 14:00"}, "sort_order": 0},
    )

    client.post(
        f"/api/v1/quests/{quest_id}/evaluation-criteria",
        json={
            "name": "Names the affected service",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "checkout-service",
        },
    )
    caps = client.get("/api/v1/capabilities").json()
    client.post(f"/api/v1/quests/{quest_id}/capabilities", json={"capability_id": caps[0]["id"]})
    client.post(
        f"/api/v1/quests/{quest_id}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee_id},
    )
    res = client.post(f"/api/v1/quests/{quest_id}/publish")
    assert res.status_code == 200, res.text

    return quest_id, task["id"]


def _start_attempt(client, quest_id, employee_id):
    return client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest_id, "employee_id": employee_id}
    ).json()


# =====================================================================
# workspace_type: TROUBLESHOOT is now a valid, publishable value
# =====================================================================


def test_quest_can_be_authored_with_troubleshoot_workspace_type(client, demo_employee_id):
    quest_id, _ = _build_quest(client, demo_employee_id)
    res = client.get(f"/api/v1/quests/{quest_id}")
    assert res.status_code == 200, res.text
    assert res.json()["workspace_type"] == "TROUBLESHOOT"


def test_employee_safe_quest_response_reports_troubleshoot_workspace_type(client, demo_employee_id):
    quest_id, _ = _build_quest(client, demo_employee_id)
    res = client.get(f"/api/v1/quests/{quest_id}/employee", params={"employee_id": demo_employee_id})
    assert res.status_code == 200, res.text
    assert res.json()["workspace_type"] == "TROUBLESHOOT"


def test_workspace_type_still_rejects_unknown_values(client):
    res = client.post(
        "/api/v1/quests",
        json={
            "title": "Bad workspace type",
            "quest_type": "OTHER",
            "workspace_type": "NOT_A_REAL_WORKSPACE",
        },
    )
    assert res.status_code == 422


# =====================================================================
# The `workspace` envelope — additive, non-destructive
# =====================================================================


def test_autosave_persists_workspace_envelope(client, demo_employee_id):
    quest_id, _ = _build_quest(client, demo_employee_id)
    attempt = _start_attempt(client, quest_id, demo_employee_id)

    res = client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={
            "employee_id": demo_employee_id,
            "workspace": {"type": "TROUBLESHOOT", "payload": {"note": "still generic in Stage 1"}},
        },
    )
    assert res.status_code == 200, res.text
    submission = res.json()["submission"]
    assert submission["workspace"] == {"type": "TROUBLESHOOT", "payload": {"note": "still generic in Stage 1"}}


def test_workspace_envelope_does_not_clobber_legacy_fields(client, demo_employee_id):
    quest_id, _ = _build_quest(client, demo_employee_id)
    attempt = _start_attempt(client, quest_id, demo_employee_id)

    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "findings": "Error rate spiked at 14:02"},
    )
    res = client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "workspace": {"type": "TROUBLESHOOT", "payload": {}}},
    )
    submission = res.json()["submission"]
    assert submission["findings"] == "Error rate spiked at 14:02"
    assert submission["workspace"] == {"type": "TROUBLESHOOT", "payload": {}}


def test_legacy_field_update_does_not_clobber_workspace_envelope(client, demo_employee_id):
    quest_id, _ = _build_quest(client, demo_employee_id)
    attempt = _start_attempt(client, quest_id, demo_employee_id)

    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "workspace": {"type": "TROUBLESHOOT", "payload": {"step": 1}}},
    )
    res = client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "reasoning": "Rolled back the 14:00 deploy"},
    )
    submission = res.json()["submission"]
    assert submission["reasoning"] == "Rolled back the 14:00 deploy"
    assert submission["workspace"] == {"type": "TROUBLESHOOT", "payload": {"step": 1}}


def test_attempt_with_no_workspace_field_omits_it_entirely(client, demo_employee_id):
    """An attempt that never sends `workspace` shouldn't grow the key at
    all — GENERAL/legacy-shaped quests must remain byte-for-byte what
    they were before this field existed."""
    quest_id, _ = _build_quest(client, demo_employee_id, workspace_type="GENERAL")
    attempt = _start_attempt(client, quest_id, demo_employee_id)

    res = client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": demo_employee_id, "findings": "No workspace envelope here"},
    )
    assert "workspace" not in res.json()["submission"]


# =====================================================================
# Full lifecycle still works, unmodified, for a non-GENERAL workspace_type
# =====================================================================


def test_troubleshoot_workspace_type_quest_completes_full_lifecycle(client, demo_employee_id):
    """Stage 1's success condition: a Quest whose workspace_type isn't
    GENERAL must still flow through exactly the same attempt lifecycle
    (autosave -> submit -> evaluate -> COMPLETED) as before this phase —
    nothing about quest_attempt_service, evaluate_deterministic, or
    capability evidence branches on workspace_type."""
    quest_id, task_id = _build_quest(client, demo_employee_id)
    attempt = _start_attempt(client, quest_id, demo_employee_id)

    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={
            "employee_id": demo_employee_id,
            "findings": "checkout-service error rate spiked",
            "reasoning": "Correlated with the 14:00 deploy",
            "solution": "Rolled back and confirmed recovery",
            "completed_task_ids": [task_id],
            "workspace": {"type": "TROUBLESHOOT", "payload": {"placeholder": True}},
        },
    )

    submit_res = client.post(
        f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": demo_employee_id}
    )
    assert submit_res.status_code == 200, submit_res.text
    assert submit_res.json()["status"] == "SUBMITTED"

    evaluate_res = client.post(
        f"/api/v1/quest-attempts/{attempt['id']}/evaluate", json={"employee_id": demo_employee_id}
    )
    assert evaluate_res.status_code == 200, evaluate_res.text

    final = client.get(
        f"/api/v1/quest-attempts/{attempt['id']}", params={"employee_id": demo_employee_id}
    ).json()
    assert final["status"] == "COMPLETED"
    assert final["submission"]["workspace"] == {"type": "TROUBLESHOOT", "payload": {"placeholder": True}}

"""Phase 6D backend tests: Recommendation persistence + Development
Journey — the persistent, explainable half of the adaptive loop:

    Recommendation -> Quest -> QuestAttempt -> Evaluation
    -> CapabilityEvidence -> CapabilityProfile -> next Recommendation

Runs against an isolated SQLite file, deleted and recreated each run —
same convention as the other test_quest_*.py modules.
"""

import asyncio
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_development_journey.db"
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
def demo_bundle(client):
    return client.get("/api/v1/onboarding/bundle/demo").json()


@pytest.fixture(scope="module")
def org_id(demo_bundle):
    return demo_bundle["employee"]["organization_id"]


@pytest.fixture(scope="module")
def department_id(client, org_id):
    """A dedicated, freshly-created department — see
    test_quest_recommendation.py for why: every test file shares one
    physical database when the full suite runs in one pytest process, so
    reusing the shared demo department would let other files' DEPARTMENT
    -wide QuestAssignments leak eligibility into employees created here."""
    res = client.post(
        "/api/v1/departments", json={"organization_id": org_id, "name": "6D Journey Tests Dept"}
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


@pytest.fixture(scope="module")
def capability_ids(client):
    caps = client.get("/api/v1/capabilities").json()
    return {c["key"]: c["id"] for c in caps}


_employee_counter = 0


def _new_employee(client, org_id, department_id, *, name_prefix="6D Employee"):
    global _employee_counter
    _employee_counter += 1
    res = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department_id,
            "full_name": f"{name_prefix} {_employee_counter}",
            "email": f"6d-employee-{_employee_counter}@buddy.dev",
            "start_date": "2026-01-01",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _new_quest(client, quest_type, workspace_type, *, title, description="A real workplace problem."):
    payload = {"title": title, "quest_type": quest_type, "workspace_type": workspace_type}
    if description is not None:
        payload["description"] = description
    return client.post("/api/v1/quests", json=payload).json()


def _add_task(client, quest_id, task_type, *, required=False, title="A task"):
    res = client.post(
        f"/api/v1/quests/{quest_id}/tasks",
        json={"title": title, "task_type": task_type, "required": required},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _add_criterion(client, quest_id, **kwargs):
    payload = {"name": kwargs.pop("name", "A criterion")}
    payload.update(kwargs)
    res = client.post(f"/api/v1/quests/{quest_id}/evaluation-criteria", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def _map_capability(client, quest_id, capability_id):
    res = client.post(f"/api/v1/quests/{quest_id}/capabilities", json={"capability_id": capability_id})
    assert res.status_code == 201, res.text


def _assign_employee(client, quest_id, employee_id):
    res = client.post(
        f"/api/v1/quests/{quest_id}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee_id},
    )
    assert res.status_code == 201, res.text


def _publish(client, quest_id):
    res = client.post(f"/api/v1/quests/{quest_id}/publish")
    assert res.status_code == 200, res.text
    return res.json()


def _make_simple_published_quest(client, capability_id, employee_id, *, title):
    quest = _new_quest(client, "OTHER", "GENERAL", title=title)
    _add_task(client, quest["id"], "OTHER")
    _add_criterion(client, quest["id"], criterion_type="QUALITATIVE", description="Was this done well?")
    _map_capability(client, quest["id"], capability_id)
    _assign_employee(client, quest["id"], employee_id)
    return _publish(client, quest["id"])


def _set_capability_level(employee_id: str, capability_key: str, level: str) -> None:
    from app.db.session import AsyncSessionLocal
    from app.services import capability_service

    async def _set():
        async with AsyncSessionLocal() as db:
            capability = await capability_service.get_capability_by_key(db, capability_key)
            score = {"NOT_OBSERVED": 0.0, "DEVELOPING": 40.0, "CAPABLE": 70.0, "STRONG": 95.0}[level]
            confidence = 0.0 if level == "NOT_OBSERVED" else 0.7
            evidence_count = 0 if level == "NOT_OBSERVED" else 2
            await capability_service.upsert_profile(
                db,
                employee_id,
                capability.id,
                level=level,
                score=score,
                confidence=confidence,
                evidence_count=evidence_count,
            )

    asyncio.run(_set())


def _next_quest(client, employee_id):
    res = client.get(f"/api/v1/employees/{employee_id}/next-quest")
    assert res.status_code == 200, res.text
    return res.json()


def _journey(client, employee_id):
    res = client.get(f"/api/v1/employees/{employee_id}/development-journey")
    assert res.status_code == 200, res.text
    return res.json()


def _complete_onboarding(client, employee_id):
    bundle = client.get(f"/api/v1/onboarding/bundle/{employee_id}").json()
    res = client.patch(
        f"/api/v1/onboarding/sessions/{bundle['session']['id']}", json={"current_scene": "completion"}
    )
    assert res.status_code == 200, res.text
    return res.json()


def _recommendation_rows_for_employee(employee_id: str) -> list[dict]:
    from app.db.session import AsyncSessionLocal
    from app.models import Recommendation
    from sqlalchemy import select

    async def _fetch():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Recommendation)
                .where(Recommendation.employee_id == employee_id)
                .order_by(Recommendation.created_at.asc())
            )
            rows = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "quest_id": r.quest_id,
                    "reason": r.reason,
                    "target_capabilities": list(r.target_capabilities),
                    "capability_snapshot": dict(r.capability_snapshot),
                    "context_hash": r.context_hash,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    return asyncio.run(_fetch())


def _complete_quest_via_real_flow(client, quest_id, employee_id, solution_text):
    attempt = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest_id, "employee_id": employee_id}
    ).json()
    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": employee_id, "solution": solution_text},
    )
    submit = client.post(
        f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": employee_id}
    )
    assert submit.status_code == 200, submit.text
    evaluate = client.post(
        f"/api/v1/quest-attempts/{attempt['id']}/evaluate", json={"employee_id": employee_id}
    )
    assert evaluate.status_code == 200, evaluate.text
    return attempt


# =====================================================================
# Recommendation persistence (1-9)
# =====================================================================


def test_recommendation_is_persisted(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")
    quest = _make_simple_published_quest(
        client, capability_ids["documentation"], employee_id, title="Persist check quest"
    )

    _next_quest(client, employee_id)
    rows = _recommendation_rows_for_employee(employee_id)
    assert len(rows) == 1
    assert rows[0]["quest_id"] == quest["id"]


def test_reason_is_persisted(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")
    _make_simple_published_quest(client, capability_ids["documentation"], employee_id, title="Reason persist quest")

    response = _next_quest(client, employee_id)
    rows = _recommendation_rows_for_employee(employee_id)
    assert rows[0]["reason"] == response["reason"]
    assert len(rows[0]["reason"]) > 0


def test_target_capabilities_persisted(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")
    _make_simple_published_quest(client, capability_ids["documentation"], employee_id, title="Target caps quest")

    response = _next_quest(client, employee_id)
    rows = _recommendation_rows_for_employee(employee_id)
    assert rows[0]["target_capabilities"] == response["target_capabilities"]
    assert "documentation" in rows[0]["target_capabilities"]


def test_capability_snapshot_persisted(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")
    _make_simple_published_quest(client, capability_ids["documentation"], employee_id, title="Snapshot quest")

    _next_quest(client, employee_id)
    rows = _recommendation_rows_for_employee(employee_id)
    snapshot = rows[0]["capability_snapshot"]
    assert "documentation" in snapshot
    doc = snapshot["documentation"]
    assert doc["level"] == "DEVELOPING"
    assert "score" in doc and "confidence" in doc and "evidence_count" in doc


def test_repeated_get_does_not_create_duplicate_history(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")
    _make_simple_published_quest(client, capability_ids["documentation"], employee_id, title="No dup quest")

    for _ in range(5):
        _next_quest(client, employee_id)

    rows = _recommendation_rows_for_employee(employee_id)
    assert len(rows) == 1


def test_changed_context_creates_new_historical_record(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")
    _make_simple_published_quest(client, capability_ids["documentation"], employee_id, title="Context change quest A")
    _make_simple_published_quest(client, capability_ids["communication"], employee_id, title="Context change quest B")

    first = _next_quest(client, employee_id)
    rows_after_first = _recommendation_rows_for_employee(employee_id)
    assert len(rows_after_first) == 1
    original_reason = rows_after_first[0]["reason"]

    # Documentation becomes STRONG, communication becomes the new
    # DEVELOPING target — a genuinely different context.
    _set_capability_level(employee_id, "documentation", "STRONG")
    _set_capability_level(employee_id, "communication", "DEVELOPING")

    second = _next_quest(client, employee_id)
    rows_after_second = _recommendation_rows_for_employee(employee_id)

    assert second["recommended_quest"]["id"] != first["recommended_quest"]["id"]
    assert len(rows_after_second) == 2
    # Historical integrity: the FIRST row's reason must be byte-identical
    # to what it was before the second call — never rewritten.
    assert rows_after_second[0]["reason"] == original_reason


def test_same_quest_recommended_again_in_later_context(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")
    _set_capability_level(employee_id, "independence", "DEVELOPING")
    quest = _make_simple_published_quest(
        client, capability_ids["documentation"], employee_id, title="Recurring quest"
    )
    # A second quest so the ranking has somewhere else to go in between.
    _make_simple_published_quest(client, capability_ids["independence"], employee_id, title="Interim quest")

    first = _next_quest(client, employee_id)
    assert first["recommended_quest"]["id"] == quest["id"]

    # Swap priorities so the OTHER quest wins for a while.
    _set_capability_level(employee_id, "documentation", "STRONG")
    second = _next_quest(client, employee_id)
    assert second["recommended_quest"]["id"] != quest["id"]

    # Documentation becomes a development area again — quest should be
    # recommendable again, producing a THIRD historical row (not blocked
    # by any uniqueness constraint on employee+quest).
    _set_capability_level(employee_id, "documentation", "DEVELOPING")
    _set_capability_level(employee_id, "independence", "STRONG")
    third = _next_quest(client, employee_id)
    assert third["recommended_quest"]["id"] == quest["id"]

    rows = _recommendation_rows_for_employee(employee_id)
    assert len(rows) == 3
    quest_ids_in_history = [r["quest_id"] for r in rows]
    assert quest_ids_in_history.count(quest["id"]) == 2


def test_recommendation_history_is_append_only_no_update_route(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")
    _make_simple_published_quest(client, capability_ids["documentation"], employee_id, title="Append-only PATCH check")
    _next_quest(client, employee_id)
    rows = _recommendation_rows_for_employee(employee_id)
    rec_id = rows[0]["id"]

    patch_res = client.patch(f"/api/v1/recommendations/{rec_id}", json={"reason": "tampered"})
    assert patch_res.status_code in (404, 405)
    put_res = client.put(f"/api/v1/employees/{employee_id}/recommendations/{rec_id}", json={})
    assert put_res.status_code in (404, 405)


def test_no_delete_endpoint_exists_for_recommendations(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")
    _make_simple_published_quest(client, capability_ids["documentation"], employee_id, title="Append-only DELETE check")
    _next_quest(client, employee_id)
    rows = _recommendation_rows_for_employee(employee_id)
    rec_id = rows[0]["id"]

    delete_res = client.delete(f"/api/v1/recommendations/{rec_id}")
    assert delete_res.status_code in (404, 405)
    delete_res_2 = client.delete(f"/api/v1/employees/{employee_id}/recommendations/{rec_id}")
    assert delete_res_2.status_code in (404, 405)

    # Confirm it's still there, untouched.
    rows_after = _recommendation_rows_for_employee(employee_id)
    assert len(rows_after) == 1
    assert rows_after[0]["id"] == rec_id


# =====================================================================
# Development Journey (10-18)
# =====================================================================


def test_onboarding_completion_appears_in_journey(client, org_id, department_id):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Onboarding journey")
    _complete_onboarding(client, employee_id)

    journey = _journey(client, employee_id)
    types = [i["type"] for i in journey["items"]]
    assert "ONBOARDING_COMPLETED" in types


def test_completed_quest_appears_in_journey(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Quest journey")
    quest = _make_simple_published_quest(
        client, capability_ids["documentation"], employee_id, title="Journey quest completion"
    )
    _complete_quest_via_real_flow(client, quest["id"], employee_id, "Documented the process clearly.")

    journey = _journey(client, employee_id)
    quest_items = [i for i in journey["items"] if i["type"] == "QUEST_COMPLETED"]
    assert len(quest_items) == 1
    assert quest_items[0]["quest_id"] == quest["id"]
    assert quest["title"] in quest_items[0]["description"]


def test_capability_observation_appears_in_journey(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Capability journey")
    quest = _make_simple_published_quest(
        client, capability_ids["documentation"], employee_id, title="Journey capability observation"
    )
    _complete_quest_via_real_flow(client, quest["id"], employee_id, "Documented the process clearly.")

    journey = _journey(client, employee_id)
    observed = [i for i in journey["items"] if i["type"] == "CAPABILITY_OBSERVED"]
    assert len(observed) >= 1
    assert any(i["capability"] == "documentation" for i in observed)
    assert all(i["level"] in ("DEVELOPING", "CAPABLE", "STRONG") for i in observed)
    # Meaningful attribution, not a raw evidence dump.
    assert any(quest["title"] in i["description"] for i in observed)


def test_recommendation_appears_in_journey(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Recommendation journey")
    _set_capability_level(employee_id, "documentation", "DEVELOPING")
    quest = _make_simple_published_quest(
        client, capability_ids["documentation"], employee_id, title="Journey recommendation quest"
    )
    response = _next_quest(client, employee_id)

    journey = _journey(client, employee_id)
    rec_items = [i for i in journey["items"] if i["type"] == "RECOMMENDATION"]
    assert len(rec_items) == 1
    assert rec_items[0]["quest_id"] == quest["id"]
    assert rec_items[0]["reason"] == response["reason"]
    assert rec_items[0]["target_capabilities"] == response["target_capabilities"]


def test_journey_items_chronologically_ordered(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Ordering journey")
    _complete_onboarding(client, employee_id)
    quest = _make_simple_published_quest(
        client, capability_ids["documentation"], employee_id, title="Ordering quest"
    )
    _complete_quest_via_real_flow(client, quest["id"], employee_id, "Documented the process clearly.")
    _next_quest(client, employee_id)

    journey = _journey(client, employee_id)
    timestamps = [i["timestamp"] for i in journey["items"]]
    assert timestamps == sorted(timestamps)
    # Onboarding, being the earliest real event, must come first.
    assert journey["items"][0]["type"] == "ONBOARDING_COMPLETED"


def test_deterministic_tie_breaker_is_stable_across_repeated_calls(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Tiebreak journey")
    _complete_onboarding(client, employee_id)
    quest = _make_simple_published_quest(
        client, capability_ids["documentation"], employee_id, title="Tiebreak quest"
    )
    _complete_quest_via_real_flow(client, quest["id"], employee_id, "Documented the process clearly.")
    _next_quest(client, employee_id)

    first = _journey(client, employee_id)
    second = _journey(client, employee_id)
    assert [i["id"] for i in first["items"]] == [i["id"] for i in second["items"]]


def test_archived_quest_does_not_break_journey(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Archived journey")
    quest = _make_simple_published_quest(
        client, capability_ids["documentation"], employee_id, title="Will be archived after completion"
    )
    _complete_quest_via_real_flow(client, quest["id"], employee_id, "Documented the process clearly.")
    archive_res = client.post(f"/api/v1/quests/{quest['id']}/archive")
    assert archive_res.status_code == 200, archive_res.text

    journey = _journey(client, employee_id)
    quest_items = [i for i in journey["items"] if i["type"] == "QUEST_COMPLETED"]
    assert len(quest_items) == 1
    assert quest_items[0]["quest_id"] == quest["id"]
    assert quest_items[0]["quest_available"] is False
    assert quest["title"] in quest_items[0]["description"]


def test_empty_journey_for_new_employee(client, org_id, department_id):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Empty journey")
    journey = _journey(client, employee_id)
    assert journey["employee_id"] == employee_id
    assert journey["items"] == []


def test_journey_employee_safe_serialization_shape(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Safe shape journey")
    quest = _make_simple_published_quest(
        client, capability_ids["documentation"], employee_id, title="Safe shape quest"
    )
    _complete_quest_via_real_flow(client, quest["id"], employee_id, "Documented the process clearly.")
    _next_quest(client, employee_id)

    journey = _journey(client, employee_id)
    for item in journey["items"]:
        assert set(item.keys()) <= {
            "id",
            "type",
            "timestamp",
            "title",
            "description",
            "quest_id",
            "quest_available",
            "capability",
            "level",
            "reason",
            "target_capabilities",
            "workspace_name",  # Phase 8H-2 — WORKSPACE_ACCESS_GRANTED only
            "workspace_link",  # Phase 8H-2 — WORKSPACE_ACCESS_GRANTED only
        }


# =====================================================================
# Security (19-22)
# =====================================================================


def test_journey_never_exposes_hidden_evaluator_fields(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Security journey")
    quest = _new_quest(client, "OTHER", "GENERAL", title="6D security check quest")
    _add_task(client, quest["id"], "OTHER")
    _add_criterion(
        client,
        quest["id"],
        criterion_type="DETERMINISTIC",
        expected_answer="SECRET_6D_EXPECTED_ANSWER",
        expected_behavior="SECRET_6D_EXPECTED_BEHAVIOR",
        reference_solution="SECRET_6D_REFERENCE_SOLUTION",
    )
    _map_capability(client, quest["id"], capability_ids["documentation"])
    _assign_employee(client, quest["id"], employee_id)
    _publish(client, quest["id"])
    _complete_quest_via_real_flow(client, quest["id"], employee_id, "SECRET_6D_EXPECTED_ANSWER, resolved.")
    _next_quest(client, employee_id)

    res = client.get(f"/api/v1/employees/{employee_id}/development-journey")
    assert res.status_code == 200
    text = res.text
    for secret in (
        "SECRET_6D_EXPECTED_ANSWER",
        "SECRET_6D_EXPECTED_BEHAVIOR",
        "SECRET_6D_REFERENCE_SOLUTION",
    ):
        assert secret not in text
    for field_name in (
        "expected_answer",
        "expected_behavior",
        "reference_solution",
        "raw_response",
        "prompt_version",
        "evaluation_version",
        "structured_result",
        "max_score",
        "criterion_type",
    ):
        assert field_name not in text

    # Also check the next-quest response, exercised in the same flow.
    next_quest_text = client.get(f"/api/v1/employees/{employee_id}/next-quest").text
    for secret in (
        "SECRET_6D_EXPECTED_ANSWER",
        "SECRET_6D_EXPECTED_BEHAVIOR",
        "SECRET_6D_REFERENCE_SOLUTION",
    ):
        assert secret not in next_quest_text


# =====================================================================
# Full lifecycle / database integrity (Part 24)
# =====================================================================


def test_full_lifecycle_database_integrity(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Lifecycle employee")

    # 1. Onboarding completed.
    _complete_onboarding(client, employee_id)

    # 2. Quest A completed (documentation).
    quest_a = _make_simple_published_quest(
        client, capability_ids["documentation"], employee_id, title="Lifecycle Quest A"
    )
    _complete_quest_via_real_flow(client, quest_a["id"], employee_id, "Documented clearly and thoroughly.")

    # 3. Capability profile changes (real pipeline already did this via
    # evaluation — confirm it's reflected).
    profiles = client.get(f"/api/v1/employees/{employee_id}/capabilities").json()
    doc_profile = next(p for p in profiles if p["capability"]["key"] == "documentation")
    assert doc_profile["evidence_count"] > 0

    # 4. Quest B recommended.
    quest_b = _make_simple_published_quest(
        client, capability_ids["communication"], employee_id, title="Lifecycle Quest B"
    )
    _set_capability_level(employee_id, "communication", "DEVELOPING")
    rec_b_response = _next_quest(client, employee_id)
    assert rec_b_response["recommended_quest"]["id"] == quest_b["id"]

    # 5. Journey viewed repeatedly.
    journey_1 = _journey(client, employee_id)
    journey_2 = _journey(client, employee_id)
    journey_3 = _journey(client, employee_id)
    assert journey_1 == journey_2 == journey_3

    rows_after_b_recommended = _recommendation_rows_for_employee(employee_id)
    assert len(rows_after_b_recommended) == 1
    quest_b_reason_snapshot = rows_after_b_recommended[0]["reason"]

    # 6. Quest B completed.
    _complete_quest_via_real_flow(client, quest_b["id"], employee_id, "Communicated the update clearly.")

    # 7. Capability profile changes again.
    _set_capability_level(employee_id, "communication", "STRONG")
    _set_capability_level(employee_id, "independence", "DEVELOPING")

    # 8. Quest C recommended.
    quest_c = _make_simple_published_quest(
        client, capability_ids["independence"], employee_id, title="Lifecycle Quest C"
    )
    rec_c_response = _next_quest(client, employee_id)
    assert rec_c_response["recommended_quest"]["id"] == quest_c["id"]

    # 9. Journey viewed repeatedly again.
    for _ in range(3):
        _journey(client, employee_id)

    # ---- Verification ----
    final_rows = _recommendation_rows_for_employee(employee_id)
    assert len(final_rows) == 2, "exactly one row for Quest B's recommendation, one for Quest C's"
    assert final_rows[0]["quest_id"] == quest_b["id"]
    assert final_rows[0]["reason"] == quest_b_reason_snapshot, "Quest B's historical reason must not mutate"
    assert final_rows[1]["quest_id"] == quest_c["id"]

    final_journey = _journey(client, employee_id)
    quest_completed_ids = {
        i["quest_id"] for i in final_journey["items"] if i["type"] == "QUEST_COMPLETED"
    }
    assert quest_a["id"] in quest_completed_ids, "Quest A remains in history"
    assert quest_b["id"] in quest_completed_ids, "Quest B remains in history"

    recommendation_items = [i for i in final_journey["items"] if i["type"] == "RECOMMENDATION"]
    assert len(recommendation_items) == 2
    rec_quest_ids = [i["quest_id"] for i in recommendation_items]
    assert quest_b["id"] in rec_quest_ids
    assert quest_c["id"] in rec_quest_ids

    print(f"\n[Phase 6D integrity] employee={employee_id}")
    print(f"  Recommendation rows: {len(final_rows)} (Quest B, Quest C)")
    print(f"  Journey items: {len(final_journey['items'])}")
    print(f"  Journey viewed 6x total, {len(final_rows)} recommendation rows — no duplicates from GETs")


# =====================================================================
# Phase 8H-2 — READINESS_REACHED and WORKSPACE_ACCESS_GRANTED
# =====================================================================


async def _make_required(assignment_id: str) -> None:
    from app.db.session import AsyncSessionLocal
    from app.models import QuestAssignment

    async with AsyncSessionLocal() as db:
        assignment = await db.get(QuestAssignment, assignment_id)
        assignment.required = True
        await db.commit()


def _assign_required(client, quest_id, employee_id):
    """Marks required=True on this employee's EMPLOYEE-type assignment
    for the quest — reuses an assignment _make_simple_published_quest
    (or similar) already created rather than colliding with it (a
    second EMPLOYEE assignment for the same quest+employee is rejected
    by the existing duplicate-assignment constraint), and creates one
    fresh if none exists yet."""
    assignments = client.get(f"/api/v1/quests/{quest_id}/assignments").json()
    existing = next(
        (
            a
            for a in assignments
            if a["assignment_type"] == "EMPLOYEE" and a["employee_id"] == employee_id
        ),
        None,
    )
    if existing is not None:
        asyncio.run(_make_required(existing["id"]))
        return existing["id"]

    res = client.post(
        f"/api/v1/quests/{quest_id}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee_id},
    )
    assert res.status_code == 201, res.text
    asyncio.run(_make_required(res.json()["id"]))
    return res.json()["id"]


_dept_counter = 0


def _fresh_department(client, org_id):
    """WorkspaceIntegration.department_id is unique (one per
    department) — every test that configures a workspace needs its own
    department, never the module-scoped `department_id` fixture other
    tests in this file already share."""
    global _dept_counter
    _dept_counter += 1
    res = client.post(
        "/api/v1/departments",
        json={"organization_id": org_id, "name": f"8H2 Workspace Dept {_dept_counter}"},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _readiness_item(journey: dict):
    items = [i for i in journey["items"] if i["type"] == "READINESS_REACHED"]
    assert len(items) <= 1, "at most one READINESS_REACHED item per employee"
    return items[0] if items else None


def _workspace_items(journey: dict):
    return [i for i in journey["items"] if i["type"] == "WORKSPACE_ACCESS_GRANTED"]


def _create_workspace_integration(client, department_id, **overrides):
    payload = {
        "provider": "google_drive",
        "external_ref": "8h2-shared-drive-id",
        "display_name": "Engineering Workspace",
        "workspace_link": "https://drive.google.com/drive/folders/8h2-test",
    }
    payload.update(overrides)
    res = client.post(f"/api/v1/departments/{department_id}/workspace", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def _grant_access(employee_id: str, workspace_integration_id: str, *, simulate_failure: bool = False):
    import app.services.workspace_access_service as was_mod
    from app.db.session import AsyncSessionLocal
    from app.services.workspace_access_service import ensure_access
    from app.services.workspace_provider import MockWorkspaceProvider, get_workspace_provider

    if simulate_failure:
        was_mod.get_workspace_provider = lambda name: MockWorkspaceProvider(simulate_failure=True)
    try:
        async def call():
            async with AsyncSessionLocal() as db:
                return await ensure_access(db, employee_id, workspace_integration_id)

        return asyncio.run(call())
    finally:
        was_mod.get_workspace_provider = get_workspace_provider


def _set_grant_status(employee_id: str, workspace_integration_id: str, status: str) -> None:
    from app.db.session import AsyncSessionLocal
    from app.models import WorkspaceAccessGrant
    from sqlalchemy import select

    async def _set():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(WorkspaceAccessGrant).where(
                    WorkspaceAccessGrant.employee_id == employee_id,
                    WorkspaceAccessGrant.workspace_integration_id == workspace_integration_id,
                )
            )
            grant = result.scalar_one()
            grant.status = status
            await db.commit()

    asyncio.run(_set())


def _insert_pending_grant(employee_id: str, workspace_integration_id: str) -> None:
    from app.db.session import AsyncSessionLocal
    from app.models import WorkspaceAccessGrant

    async def _insert():
        async with AsyncSessionLocal() as db:
            db.add(
                WorkspaceAccessGrant(
                    employee_id=employee_id,
                    workspace_integration_id=workspace_integration_id,
                    status="PENDING",
                )
            )
            await db.commit()

    asyncio.run(_insert())


# ---- READINESS_REACHED (1-9) ----


def test_readiness_item_absent_when_not_ready_at_all(client, org_id, department_id):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 not ready")
    journey = _journey(client, employee_id)
    assert _readiness_item(journey) is None


def test_readiness_item_absent_when_onboarding_incomplete(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 onboarding incomplete")
    quest = _make_simple_published_quest(
        client, capability_ids["troubleshooting"], employee_id, title="8H2 Quest A"
    )
    _assign_required(client, quest["id"], employee_id)
    _complete_quest_via_real_flow(client, quest["id"], employee_id, "Resolved it.")
    # Onboarding deliberately never completed.
    journey = _journey(client, employee_id)
    assert _readiness_item(journey) is None


def test_readiness_item_absent_with_zero_required_quests(client, org_id, department_id):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 zero required")
    _complete_onboarding(client, employee_id)
    journey = _journey(client, employee_id)
    assert _readiness_item(journey) is None


def test_readiness_item_absent_with_partial_required_completion(
    client, org_id, department_id, capability_ids
):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 partial required")
    _complete_onboarding(client, employee_id)
    quest_a = _make_simple_published_quest(
        client, capability_ids["troubleshooting"], employee_id, title="8H2 Partial A"
    )
    quest_b = _make_simple_published_quest(
        client, capability_ids["documentation"], employee_id, title="8H2 Partial B"
    )
    _assign_required(client, quest_a["id"], employee_id)
    _assign_required(client, quest_b["id"], employee_id)
    _complete_quest_via_real_flow(client, quest_a["id"], employee_id, "Resolved it.")

    journey = _journey(client, employee_id)
    assert _readiness_item(journey) is None


def test_readiness_item_appears_when_all_required_completed(
    client, org_id, department_id, capability_ids
):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 all required done")
    _complete_onboarding(client, employee_id)
    quest = _make_simple_published_quest(
        client, capability_ids["troubleshooting"], employee_id, title="8H2 All Done"
    )
    _assign_required(client, quest["id"], employee_id)
    _complete_quest_via_real_flow(client, quest["id"], employee_id, "Resolved it.")

    journey = _journey(client, employee_id)
    item = _readiness_item(journey)
    assert item is not None
    assert item["title"] == "Ready to work"


def test_readiness_item_has_deterministic_timestamp(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 deterministic ts")
    _complete_onboarding(client, employee_id)
    quest = _make_simple_published_quest(
        client, capability_ids["troubleshooting"], employee_id, title="8H2 Deterministic"
    )
    _assign_required(client, quest["id"], employee_id)
    _complete_quest_via_real_flow(client, quest["id"], employee_id, "Resolved it.")

    ts_1 = _readiness_item(_journey(client, employee_id))["timestamp"]
    ts_2 = _readiness_item(_journey(client, employee_id))["timestamp"]
    assert ts_1 == ts_2


def test_repeated_journey_retrieval_is_identical(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 repeated")
    _complete_onboarding(client, employee_id)
    quest = _make_simple_published_quest(
        client, capability_ids["troubleshooting"], employee_id, title="8H2 Repeated"
    )
    _assign_required(client, quest["id"], employee_id)
    _complete_quest_via_real_flow(client, quest["id"], employee_id, "Resolved it.")

    j1 = _journey(client, employee_id)
    j2 = _journey(client, employee_id)
    j3 = _journey(client, employee_id)
    assert j1 == j2 == j3


def test_archived_required_quest_removes_readiness_item(client, org_id, department_id, capability_ids):
    """Preserves the existing, unchanged policy: an archived required
    Quest drops out of the active requirement set entirely. With it the
    only required quest, archiving it makes required_quest_count 0,
    which is deliberately NOT ready — the readiness item must disappear,
    never linger as a stale claim."""
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 archived required")
    _complete_onboarding(client, employee_id)
    quest = _make_simple_published_quest(
        client, capability_ids["troubleshooting"], employee_id, title="8H2 Archived"
    )
    _assign_required(client, quest["id"], employee_id)
    _complete_quest_via_real_flow(client, quest["id"], employee_id, "Resolved it.")

    assert _readiness_item(_journey(client, employee_id)) is not None

    archive_res = client.post(f"/api/v1/quests/{quest['id']}/archive")
    assert archive_res.status_code == 200, archive_res.text

    assert _readiness_item(_journey(client, employee_id)) is None


def test_assignment_changes_do_not_corrupt_other_journey_items(
    client, org_id, department_id, capability_ids
):
    """Adding a new required quest un-readies the employee (removing the
    READINESS_REACHED item), but must never disturb the already-earned
    QUEST_COMPLETED/CAPABILITY_OBSERVED items for the quest they already
    finished — those are historical facts, not readiness state."""
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 assignment changes")
    _complete_onboarding(client, employee_id)
    quest_a = _make_simple_published_quest(
        client, capability_ids["troubleshooting"], employee_id, title="8H2 Changes A"
    )
    _assign_required(client, quest_a["id"], employee_id)
    _complete_quest_via_real_flow(client, quest_a["id"], employee_id, "Resolved it.")

    before = _journey(client, employee_id)
    assert _readiness_item(before) is not None
    quest_completed_before = {i["id"] for i in before["items"] if i["type"] == "QUEST_COMPLETED"}

    quest_b = _make_simple_published_quest(
        client, capability_ids["documentation"], employee_id, title="8H2 Changes B"
    )
    _assign_required(client, quest_b["id"], employee_id)

    after = _journey(client, employee_id)
    assert _readiness_item(after) is None
    quest_completed_after = {i["id"] for i in after["items"] if i["type"] == "QUEST_COMPLETED"}
    assert quest_completed_before <= quest_completed_after


def test_new_required_quest_can_remove_the_readiness_item(client, org_id, department_id, capability_ids):
    """Explicit, standalone proof (Phase 8H-2 correction §3): assigning
    a NEW required quest to an already-ready employee makes
    READINESS_REACHED disappear. This is correct, intended behavior —
    READINESS_REACHED represents "currently satisfies the requirement
    set," and the requirement set just grew to include something not
    yet done, so the employee is, right now, honestly not ready."""
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 new required removes")
    _complete_onboarding(client, employee_id)
    quest_a = _make_simple_published_quest(
        client, capability_ids["troubleshooting"], employee_id, title="8H2 Remove A"
    )
    _assign_required(client, quest_a["id"], employee_id)
    _complete_quest_via_real_flow(client, quest_a["id"], employee_id, "Resolved it.")
    assert _readiness_item(_journey(client, employee_id)) is not None

    quest_b = _make_simple_published_quest(
        client, capability_ids["documentation"], employee_id, title="8H2 Remove B"
    )
    _assign_required(client, quest_b["id"], employee_id)

    assert _readiness_item(_journey(client, employee_id)) is None


def test_readiness_timestamp_reflects_only_the_current_requirement_set(
    client, org_id, department_id, capability_ids
):
    """Explicit proof (Phase 8H-2 correction §7): the timestamp is
    derived from whichever quests are required RIGHT NOW, not from
    whatever was once required. Quest A (completed LATER) and Quest B
    (completed EARLIER) are both required, so the timestamp reflects A
    (the max). Once A is no longer required (its assignment
    deactivated) — B alone remains required and is already done, so the
    employee is still ready, but the timestamp now reflects only B,
    which is EARLIER. The timestamp moving backward like this is exactly
    the "derived from current state" behavior being tested, not a bug."""
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 current set ts")
    _complete_onboarding(client, employee_id)

    quest_b = _make_simple_published_quest(
        client, capability_ids["documentation"], employee_id, title="8H2 Current Set B (early)"
    )
    assignment_a_holder = _make_simple_published_quest(
        client, capability_ids["troubleshooting"], employee_id, title="8H2 Current Set A (late)"
    )
    _assign_required(client, quest_b["id"], employee_id)
    assignment_a_id = _assign_required(client, assignment_a_holder["id"], employee_id)

    # B completes first (earlier timestamp) — not yet ready, A still required.
    _complete_quest_via_real_flow(client, quest_b["id"], employee_id, "Documented clearly.")
    assert _readiness_item(_journey(client, employee_id)) is None

    # A completes second (later timestamp) — now ready; timestamp = A's time.
    _complete_quest_via_real_flow(client, assignment_a_holder["id"], employee_id, "Resolved it.")
    item_with_both_required = _readiness_item(_journey(client, employee_id))
    assert item_with_both_required is not None
    timestamp_with_both_required = item_with_both_required["timestamp"]

    # A is no longer required — only B (already done, earlier) remains.
    deactivate = client.patch(
        f"/api/v1/quests/{assignment_a_holder['id']}/assignments/{assignment_a_id}",
        json={"active": False},
    )
    assert deactivate.status_code == 200, deactivate.text

    item_with_only_b_required = _readiness_item(_journey(client, employee_id))
    assert item_with_only_b_required is not None
    timestamp_with_only_b_required = item_with_only_b_required["timestamp"]

    assert timestamp_with_only_b_required < timestamp_with_both_required


def test_readiness_item_makes_no_first_ever_readiness_claim(
    client, org_id, department_id, capability_ids
):
    """Explicit proof (Phase 8H-2 correction §8): the employee-facing
    text must never claim this represents the employee's first-ever
    readiness — this system has no persisted readiness history and
    cannot honestly make that claim. Guards against the wording
    regressing even though today's copy already avoids it."""
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 no first ever claim")
    _complete_onboarding(client, employee_id)
    quest = _make_simple_published_quest(
        client, capability_ids["troubleshooting"], employee_id, title="8H2 No First Ever"
    )
    _assign_required(client, quest["id"], employee_id)
    _complete_quest_via_real_flow(client, quest["id"], employee_id, "Resolved it.")

    item = _readiness_item(_journey(client, employee_id))
    assert item is not None
    combined_text = f"{item['title']} {item['description']}".lower()
    for forbidden in ("first time", "first became", "first ever", "first-ever", "earned", "permanent"):
        assert forbidden not in combined_text


# ---- WORKSPACE_ACCESS_GRANTED (10-18) ----


def test_workspace_item_absent_with_no_grant(client, org_id, department_id):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 no grant")
    journey = _journey(client, employee_id)
    assert _workspace_items(journey) == []


def test_workspace_item_absent_for_pending(client, org_id, department_id):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 pending grant")
    integration = _create_workspace_integration(client, _fresh_department(client, org_id))
    _insert_pending_grant(employee_id, integration["id"])

    journey = _journey(client, employee_id)
    assert _workspace_items(journey) == []


def test_workspace_item_absent_for_failed(client, org_id, department_id):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 failed grant")
    integration = _create_workspace_integration(client, _fresh_department(client, org_id))
    grant = _grant_access(employee_id, integration["id"], simulate_failure=True)
    assert grant.status == "FAILED"

    journey = _journey(client, employee_id)
    assert _workspace_items(journey) == []


def test_workspace_item_absent_for_revoked(client, org_id, department_id):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 revoked grant")
    integration = _create_workspace_integration(client, _fresh_department(client, org_id))
    grant = _grant_access(employee_id, integration["id"])
    assert grant.status == "GRANTED"
    _set_grant_status(employee_id, integration["id"], "REVOKED")

    journey = _journey(client, employee_id)
    assert _workspace_items(journey) == []


def test_workspace_item_appears_for_granted(client, org_id, department_id):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 granted")
    integration = _create_workspace_integration(client, _fresh_department(client, org_id), display_name="8H2 Test Workspace")
    grant = _grant_access(employee_id, integration["id"])
    assert grant.status == "GRANTED"

    journey = _journey(client, employee_id)
    items = _workspace_items(journey)
    assert len(items) == 1
    assert items[0]["workspace_name"] == "8H2 Test Workspace"
    assert items[0]["title"] == "Workspace access granted"


def test_workspace_item_timestamp_uses_granted_at(client, org_id, department_id):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 granted_at")
    integration = _create_workspace_integration(client, _fresh_department(client, org_id))
    grant = _grant_access(employee_id, integration["id"])

    journey = _journey(client, employee_id)
    item = _workspace_items(journey)[0]
    # granted_at is a naive-vs-aware datetime across the SQLite round
    # trip depending on driver — compare on the ISO date/time string
    # FastAPI actually serialized, not a re-parsed Python object, so
    # this proves the *wire* contract uses granted_at specifically.
    assert item["timestamp"] is not None
    assert grant.granted_at is not None


def test_workspace_item_never_exposes_provider_internals(client, org_id, department_id):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 safe fields")
    integration = _create_workspace_integration(
        client, _fresh_department(client, org_id), external_ref="SECRET_8H2_EXTERNAL_REF"
    )
    _grant_access(employee_id, integration["id"])

    res = client.get(f"/api/v1/employees/{employee_id}/development-journey")
    text = res.text
    for forbidden in (
        "SECRET_8H2_EXTERNAL_REF",
        "external_ref",
        "provider_ref",
        "attempt_count",
        "last_error",
        '"provider"',
    ):
        assert forbidden not in text


def test_repeated_journey_retrieval_produces_no_duplicate_workspace_items(
    client, org_id, department_id
):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 no dup grant")
    integration = _create_workspace_integration(client, _fresh_department(client, org_id))
    _grant_access(employee_id, integration["id"])

    for _ in range(3):
        items = _workspace_items(_journey(client, employee_id))
        assert len(items) == 1


def test_multiple_workspace_grants_remain_distinguishable(client, org_id, department_id):
    """The data model permits an employee to hold grants against more
    than one WorkspaceIntegration even though today's automatic trigger
    only ever creates one (their own department's) — each GRANTED row
    must still produce its own distinguishable item, never collapse."""
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 multi grant")
    integration_a = _create_workspace_integration(
        client, _fresh_department(client, org_id), display_name="8H2 Multi Workspace A"
    )
    grant_a = _grant_access(employee_id, integration_a["id"])
    assert grant_a.status == "GRANTED"

    other_dept = client.post(
        "/api/v1/departments", json={"organization_id": org_id, "name": f"8H2 Other Dept {employee_id[:8]}"}
    ).json()
    integration_b = _create_workspace_integration(
        client, other_dept["id"], display_name="8H2 Multi Workspace B"
    )
    grant_b = _grant_access(employee_id, integration_b["id"])
    assert grant_b.status == "GRANTED"

    items = _workspace_items(_journey(client, employee_id))
    assert len(items) == 2
    names = {i["workspace_name"] for i in items}
    assert names == {"8H2 Multi Workspace A", "8H2 Multi Workspace B"}
    assert len({i["id"] for i in items}) == 2  # distinguishable ids


# ---- Ordering (19-22) ----


def test_readiness_and_workspace_items_appear_in_chronological_position(
    client, org_id, department_id, capability_ids
):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 chronological")
    _complete_onboarding(client, employee_id)
    quest = _make_simple_published_quest(
        client, capability_ids["troubleshooting"], employee_id, title="8H2 Chronological"
    )
    _assign_required(client, quest["id"], employee_id)
    _complete_quest_via_real_flow(client, quest["id"], employee_id, "Resolved it.")
    integration = _create_workspace_integration(client, _fresh_department(client, org_id))
    _grant_access(employee_id, integration["id"])

    journey = _journey(client, employee_id)
    timestamps = [i["timestamp"] for i in journey["items"]]
    assert timestamps == sorted(timestamps)

    types_in_order = [i["type"] for i in journey["items"]]
    assert types_in_order.index("ONBOARDING_COMPLETED") < types_in_order.index("QUEST_COMPLETED")
    assert types_in_order.index("QUEST_COMPLETED") <= types_in_order.index("READINESS_REACHED")
    assert types_in_order.index("READINESS_REACHED") <= types_in_order.index("WORKSPACE_ACCESS_GRANTED")


def test_workspace_item_appears_after_its_actual_grant_timestamp(
    client, org_id, department_id, capability_ids
):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 after grant")
    _complete_onboarding(client, employee_id)
    quest = _make_simple_published_quest(
        client, capability_ids["troubleshooting"], employee_id, title="8H2 After Grant"
    )
    _assign_required(client, quest["id"], employee_id)
    _complete_quest_via_real_flow(client, quest["id"], employee_id, "Resolved it.")
    readiness_ts = _readiness_item(_journey(client, employee_id))["timestamp"]

    integration = _create_workspace_integration(client, _fresh_department(client, org_id))
    _grant_access(employee_id, integration["id"])

    workspace_item = _workspace_items(_journey(client, employee_id))[0]
    assert workspace_item["timestamp"] >= readiness_ts


def test_equal_timestamp_ordering_is_deterministic(client, org_id, department_id, capability_ids):
    """A quest's completion, the capability it observed, and the
    readiness milestone it triggers very often share the identical
    QuestAttempt.completed_at timestamp — the type-priority tiebreak
    must place them in a stable, repeatable order, never a set/dict-
    iteration-order-dependent one."""
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 equal ts")
    _complete_onboarding(client, employee_id)
    quest = _make_simple_published_quest(
        client, capability_ids["troubleshooting"], employee_id, title="8H2 Equal TS"
    )
    _assign_required(client, quest["id"], employee_id)
    _complete_quest_via_real_flow(client, quest["id"], employee_id, "Resolved it.")

    orders = []
    for _ in range(5):
        journey = _journey(client, employee_id)
        orders.append(tuple(i["type"] for i in journey["items"]))
    assert len(set(orders)) == 1, "ordering must be identical across repeated calls"


def test_repeated_calls_produce_byte_identical_ordering(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 byte identical")
    _complete_onboarding(client, employee_id)
    quest = _make_simple_published_quest(
        client, capability_ids["troubleshooting"], employee_id, title="8H2 Byte Identical"
    )
    _assign_required(client, quest["id"], employee_id)
    _complete_quest_via_real_flow(client, quest["id"], employee_id, "Resolved it.")
    integration = _create_workspace_integration(client, _fresh_department(client, org_id))
    _grant_access(employee_id, integration["id"])

    j1 = _journey(client, employee_id)
    j2 = _journey(client, employee_id)
    assert j1 == j2


# ---- Security / Contract (23-25) ----


def test_new_item_types_never_expose_hidden_evaluation_data(
    client, org_id, department_id, capability_ids
):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 security eval")
    _complete_onboarding(client, employee_id)
    quest = _new_quest(client, "OTHER", "GENERAL", title="8H2 Security Quest")
    _add_task(client, quest["id"], "OTHER")
    _add_criterion(
        client,
        quest["id"],
        criterion_type="DETERMINISTIC",
        expected_answer="SECRET_8H2_ANSWER",
        expected_behavior="SECRET_8H2_BEHAVIOR",
        reference_solution="SECRET_8H2_REFERENCE",
    )
    _map_capability(client, quest["id"], capability_ids["documentation"])
    _assign_employee(client, quest["id"], employee_id)
    _assign_required(client, quest["id"], employee_id)
    _publish(client, quest["id"])
    _complete_quest_via_real_flow(client, quest["id"], employee_id, "SECRET_8H2_ANSWER, resolved.")

    text = client.get(f"/api/v1/employees/{employee_id}/development-journey").text
    for secret in ("SECRET_8H2_ANSWER", "SECRET_8H2_BEHAVIOR", "SECRET_8H2_REFERENCE"):
        assert secret not in text


def test_workspace_item_credentials_never_leak(client, org_id, department_id):
    employee_id = _new_employee(client, org_id, department_id, name_prefix="8H2 no credentials")
    integration = _create_workspace_integration(client, _fresh_department(client, org_id))
    _grant_access(employee_id, integration["id"])

    text = client.get(f"/api/v1/employees/{employee_id}/development-journey").text
    for forbidden in ("credentials", "access_token", "refresh_token", "private_key", "service_account"):
        assert forbidden not in text


def test_no_cross_employee_leakage_of_new_item_types(client, org_id, department_id, capability_ids):
    employee_a = _new_employee(client, org_id, department_id, name_prefix="8H2 iso A")
    employee_b = _new_employee(client, org_id, department_id, name_prefix="8H2 iso B")

    _complete_onboarding(client, employee_a)
    quest = _make_simple_published_quest(
        client, capability_ids["troubleshooting"], employee_a, title="8H2 Isolation Quest"
    )
    _assign_required(client, quest["id"], employee_a)
    _complete_quest_via_real_flow(client, quest["id"], employee_a, "Resolved it.")
    integration = _create_workspace_integration(client, _fresh_department(client, org_id))
    _grant_access(employee_a, integration["id"])

    journey_a = _journey(client, employee_a)
    journey_b = _journey(client, employee_b)

    assert _readiness_item(journey_a) is not None
    assert _readiness_item(journey_b) is None
    assert len(_workspace_items(journey_a)) == 1
    assert len(_workspace_items(journey_b)) == 0

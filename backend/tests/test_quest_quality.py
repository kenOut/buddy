"""Phase 6B backend tests: Quest Type requirements config
(quest_quality_config.py) and Quest Quality Validation service
(quest_quality_service.py), exercised end-to-end through the API —
publish-readiness, publish rejection/acceptance, immutability, security,
cross-quest isolation, and concurrency.

Runs against an isolated SQLite file, deleted and recreated each run —
same convention as the other test_quest_*.py modules.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_quest_quality.db"
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


@pytest.fixture(scope="module")
def capability_id(client):
    return client.get("/api/v1/capabilities").json()[0]["id"]


# ---- small, composable helpers — no giant "build everything" fixture,
# so each test can show exactly what it includes/omits ----


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


def _add_evidence(client, quest_id, *, evidence_type="TEXT", title="Some evidence"):
    res = client.post(
        f"/api/v1/quests/{quest_id}/evidence",
        json={"title": title, "evidence_type": evidence_type, "content": {}},
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


def _assign(client, quest_id, employee_id):
    res = client.post(
        f"/api/v1/quests/{quest_id}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee_id},
    )
    assert res.status_code == 201, res.text


def _readiness(client, quest_id):
    res = client.get(f"/api/v1/quests/{quest_id}/publish-readiness")
    assert res.status_code == 200, res.text
    return res.json()


def _publish(client, quest_id):
    return client.post(f"/api/v1/quests/{quest_id}/publish")


def _error_codes(readiness_body):
    return {c["code"] for c in readiness_body["errors"]}


# =====================================================================
# 1-2-3: TROUBLESHOOT
# =====================================================================


def test_valid_troubleshoot_quest_passes(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "TROUBLESHOOT", "FIX", title="Valid troubleshoot")
    _add_task(client, quest["id"], "INVESTIGATE")
    _add_evidence(client, quest["id"])
    _add_criterion(client, quest["id"], criterion_type="DETERMINISTIC", expected_answer="answer")
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    assert _readiness(client, quest["id"])["ready"] is True
    res = _publish(client, quest["id"])
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "PUBLISHED"


def test_troubleshoot_without_evidence_fails(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "TROUBLESHOOT", "FIX", title="Troubleshoot no evidence")
    _add_task(client, quest["id"], "INVESTIGATE")
    _add_criterion(client, quest["id"], criterion_type="DETERMINISTIC", expected_answer="answer")
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    body = _readiness(client, quest["id"])
    assert body["ready"] is False
    assert "MISSING_EVIDENCE" in _error_codes(body)
    res = _publish(client, quest["id"])
    assert res.status_code == 409
    assert "evidence" in res.json()["detail"].lower()


def test_troubleshoot_without_investigation_task_fails(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "TROUBLESHOOT", "FIX", title="Troubleshoot no investigation task")
    _add_evidence(client, quest["id"])
    _add_criterion(client, quest["id"], criterion_type="DETERMINISTIC", expected_answer="answer")
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    body = _readiness(client, quest["id"])
    assert body["ready"] is False
    assert "MISSING_INVESTIGATION_TASK" in _error_codes(body)
    res = _publish(client, quest["id"])
    assert res.status_code == 409


# =====================================================================
# 4-5-6: BUILD
# =====================================================================


def test_valid_build_quest_passes(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "BUILD", "BUILD", title="Valid build")
    _add_task(client, quest["id"], "BUILD")
    _add_criterion(
        client, quest["id"], criterion_type="BEHAVIORAL", expected_behavior="Ships a working endpoint"
    )
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    assert _readiness(client, quest["id"])["ready"] is True
    res = _publish(client, quest["id"])
    assert res.status_code == 200, res.text


def test_build_without_implementation_task_fails(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "BUILD", "BUILD", title="Build no implementation task")
    _add_criterion(
        client, quest["id"], criterion_type="BEHAVIORAL", expected_behavior="Ships a working endpoint"
    )
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    body = _readiness(client, quest["id"])
    assert body["ready"] is False
    assert "MISSING_TASK" in _error_codes(body)
    res = _publish(client, quest["id"])
    assert res.status_code == 409


def test_build_without_expected_outcome_fails(client, demo_employee_id, capability_id):
    """A BUILD quest with a task and a *criterion row* that exists but
    carries no real expected-behavior content still fails — existence of
    a criterion isn't the same as defining the outcome."""
    quest = _new_quest(client, "BUILD", "BUILD", title="Build no expected outcome")
    _add_task(client, quest["id"], "BUILD")
    _add_criterion(client, quest["id"], criterion_type="BEHAVIORAL")  # no expected_behavior
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    body = _readiness(client, quest["id"])
    assert body["ready"] is False
    assert "MISSING_EXPECTED_OUTCOME" in _error_codes(body)
    assert "INVALID_EVALUATION_CRITERION" in _error_codes(body)
    res = _publish(client, quest["id"])
    assert res.status_code == 409


# =====================================================================
# 7-8: DESIGN
# =====================================================================


def test_valid_design_quest_passes(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "DESIGN", "DESIGN", title="Valid design")
    _add_task(client, quest["id"], "DESIGN")
    _add_criterion(
        client, quest["id"], criterion_type="QUALITATIVE", description="Are the trade-offs well-reasoned?"
    )
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    assert _readiness(client, quest["id"])["ready"] is True
    res = _publish(client, quest["id"])
    assert res.status_code == 200, res.text


def test_design_without_meaningful_design_task_fails(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "DESIGN", "DESIGN", title="Design no design task")
    _add_task(client, quest["id"], "EXPLAIN")  # a task exists, but not a DESIGN-typed one
    _add_criterion(
        client, quest["id"], criterion_type="QUALITATIVE", description="Are the trade-offs well-reasoned?"
    )
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    body = _readiness(client, quest["id"])
    assert body["ready"] is False
    assert "MISSING_DESIGN_TASK" in _error_codes(body)
    res = _publish(client, quest["id"])
    assert res.status_code == 409


# =====================================================================
# 9: INVESTIGATE
# =====================================================================


def test_valid_investigate_quest_passes(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "INVESTIGATE", "INVESTIGATION", title="Valid investigate")
    _add_task(client, quest["id"], "INVESTIGATE")
    _add_evidence(client, quest["id"])
    _add_criterion(client, quest["id"], criterion_type="DETERMINISTIC", expected_answer="answer")
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    assert _readiness(client, quest["id"])["ready"] is True
    res = _publish(client, quest["id"])
    assert res.status_code == 200, res.text


# =====================================================================
# 10: ANALYZE
# =====================================================================


def test_analyze_requires_relevant_evidence(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "ANALYZE", "ANALYSIS", title="Analyze no evidence")
    _add_task(client, quest["id"], "ANALYZE")
    _add_criterion(client, quest["id"], criterion_type="DETERMINISTIC", expected_answer="answer")
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    body = _readiness(client, quest["id"])
    assert body["ready"] is False
    assert "MISSING_EVIDENCE" in _error_codes(body)

    _add_evidence(client, quest["id"], evidence_type="DATASET", title="Sales dataset")
    assert _readiness(client, quest["id"])["ready"] is True
    res = _publish(client, quest["id"])
    assert res.status_code == 200, res.text


def test_analyze_without_analysis_task_fails(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "ANALYZE", "ANALYSIS", title="Analyze no analysis task")
    _add_evidence(client, quest["id"], evidence_type="DATASET")
    _add_criterion(client, quest["id"], criterion_type="DETERMINISTIC", expected_answer="answer")
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    body = _readiness(client, quest["id"])
    assert "MISSING_ANALYSIS_TASK" in _error_codes(body)
    assert _publish(client, quest["id"]).status_code == 409


# =====================================================================
# 11: FIX
# =====================================================================


def test_fix_requires_problem_evidence_and_task_structure(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "FIX", "FIX", title="Fix quest")
    # Missing everything type-specific at first.
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    body = _readiness(client, quest["id"])
    codes = _error_codes(body)
    assert "MISSING_TASK" in codes  # FIX's task check shares the generic code
    assert "MISSING_EVIDENCE" in codes
    assert "MISSING_EVALUATION" in codes

    _add_task(client, quest["id"], "FIX")
    _add_evidence(client, quest["id"], evidence_type="LOGS", title="Reproduction steps")
    _add_criterion(client, quest["id"], criterion_type="BEHAVIORAL", expected_behavior="Verifies the fix with a test")

    assert _readiness(client, quest["id"])["ready"] is True
    assert _publish(client, quest["id"]).status_code == 200


# =====================================================================
# 12: CREATE_SOLUTION
# =====================================================================


def test_create_solution_requires_solution_task(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "CREATE_SOLUTION", "GENERAL", title="Create solution quest")
    _add_criterion(client, quest["id"], criterion_type="QUALITATIVE", description="Does the solution address the need?")
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    body = _readiness(client, quest["id"])
    assert "MISSING_SOLUTION_TASK" in _error_codes(body)

    _add_task(client, quest["id"], "CREATE")
    assert _readiness(client, quest["id"])["ready"] is True
    assert _publish(client, quest["id"]).status_code == 200


# =====================================================================
# 13: OTHER (generic minimum)
# =====================================================================


def test_other_uses_generic_validation(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "OTHER", "GENERAL", title="Other quest")
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    body = _readiness(client, quest["id"])
    codes = _error_codes(body)
    assert "MISSING_TASK" in codes
    assert "MISSING_EVALUATION" in codes
    # OTHER has no evidence requirement at all — never blocking.
    assert "MISSING_EVIDENCE" not in codes

    _add_task(client, quest["id"], "OTHER")
    _add_criterion(client, quest["id"], criterion_type="QUALITATIVE", description="Was this done well?")
    assert _readiness(client, quest["id"])["ready"] is True
    assert _publish(client, quest["id"]).status_code == 200


# =====================================================================
# 14-15-16: universal requirements
# =====================================================================


def test_missing_capability_fails_for_every_type(client, demo_employee_id):
    quest = _new_quest(client, "OTHER", "GENERAL", title="No capability")
    _add_task(client, quest["id"], "OTHER")
    _add_criterion(client, quest["id"], criterion_type="QUALITATIVE", description="ok")
    _assign(client, quest["id"], demo_employee_id)

    body = _readiness(client, quest["id"])
    assert "MISSING_CAPABILITY" in _error_codes(body)
    assert _publish(client, quest["id"]).status_code == 409


def test_missing_assignment_fails_for_every_type(client, capability_id):
    quest = _new_quest(client, "OTHER", "GENERAL", title="No assignment")
    _add_task(client, quest["id"], "OTHER")
    _add_criterion(client, quest["id"], criterion_type="QUALITATIVE", description="ok")
    _map_capability(client, quest["id"], capability_id)

    body = _readiness(client, quest["id"])
    assert "MISSING_ASSIGNMENT" in _error_codes(body)
    assert _publish(client, quest["id"]).status_code == 409


def test_missing_challenge_fails_for_every_type(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "OTHER", "GENERAL", title="No challenge", description=None)
    _add_task(client, quest["id"], "OTHER")
    _add_criterion(client, quest["id"], criterion_type="QUALITATIVE", description="ok")
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    body = _readiness(client, quest["id"])
    assert "MISSING_CHALLENGE" in _error_codes(body)
    assert _publish(client, quest["id"]).status_code == 409


# =====================================================================
# 17-18-19: criterion content quality
# =====================================================================


def test_invalid_deterministic_criterion_fails(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "OTHER", "GENERAL", title="Invalid deterministic criterion")
    _add_task(client, quest["id"], "OTHER")
    _add_criterion(client, quest["id"], criterion_type="DETERMINISTIC")  # no expected_answer
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    body = _readiness(client, quest["id"])
    assert "INVALID_EVALUATION_CRITERION" in _error_codes(body)
    assert _publish(client, quest["id"]).status_code == 409


def test_invalid_behavioral_criterion_fails(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "OTHER", "GENERAL", title="Invalid behavioral criterion")
    _add_task(client, quest["id"], "OTHER")
    _add_criterion(client, quest["id"], criterion_type="BEHAVIORAL")  # no expected_behavior
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    body = _readiness(client, quest["id"])
    assert "INVALID_EVALUATION_CRITERION" in _error_codes(body)
    assert _publish(client, quest["id"]).status_code == 409


def test_invalid_qualitative_criterion_fails(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "OTHER", "GENERAL", title="Invalid qualitative criterion")
    _add_task(client, quest["id"], "OTHER")
    _add_criterion(client, quest["id"], criterion_type="QUALITATIVE")  # no description or reference_solution
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    body = _readiness(client, quest["id"])
    assert "INVALID_EVALUATION_CRITERION" in _error_codes(body)
    assert _publish(client, quest["id"]).status_code == 409


def test_qualitative_criterion_accepts_reference_solution_alone(client, demo_employee_id, capability_id):
    """A QUALITATIVE criterion is well-formed with EITHER a description
    OR a reference_solution — not both required."""
    quest = _new_quest(client, "OTHER", "GENERAL", title="Qualitative with reference solution only")
    _add_task(client, quest["id"], "OTHER")
    _add_criterion(client, quest["id"], criterion_type="QUALITATIVE", reference_solution="A model answer.")
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    assert _readiness(client, quest["id"])["ready"] is True


# =====================================================================
# 20: published quest remains immutable (Phase 6B content, not just Stage 6A)
# =====================================================================


def test_published_quest_remains_immutable_under_new_rules(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "TROUBLESHOOT", "FIX", title="Immutable after 6B publish")
    _add_task(client, quest["id"], "INVESTIGATE")
    _add_evidence(client, quest["id"])
    _add_criterion(client, quest["id"], criterion_type="DETERMINISTIC", expected_answer="answer")
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)
    assert _publish(client, quest["id"]).status_code == 200

    res = client.post(
        f"/api/v1/quests/{quest['id']}/tasks", json={"title": "Sneaky", "task_type": "INVESTIGATE"}
    )
    assert res.status_code == 409, res.text
    res = client.patch(f"/api/v1/quests/{quest['id']}", json={"title": "Sneaky retitle"})
    assert res.status_code == 409, res.text


# =====================================================================
# 21: employee response never exposes hidden evaluator fields
# =====================================================================


def test_employee_response_never_exposes_hidden_evaluator_fields(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "TROUBLESHOOT", "FIX", title="6B employee-safety check")
    _add_task(client, quest["id"], "INVESTIGATE")
    _add_evidence(client, quest["id"])
    _add_criterion(
        client,
        quest["id"],
        criterion_type="DETERMINISTIC",
        expected_answer="SECRET_6B_EXPECTED_ANSWER",
        expected_behavior="SECRET_6B_EXPECTED_BEHAVIOR",
        reference_solution="SECRET_6B_REFERENCE_SOLUTION",
    )
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)
    assert _publish(client, quest["id"]).status_code == 200

    res = client.get(f"/api/v1/quests/{quest['id']}/employee", params={"employee_id": demo_employee_id})
    assert res.status_code == 200, res.text
    text = res.text
    for secret in (
        "SECRET_6B_EXPECTED_ANSWER",
        "SECRET_6B_EXPECTED_BEHAVIOR",
        "SECRET_6B_REFERENCE_SOLUTION",
    ):
        assert secret not in text
    assert "expected_answer" not in text
    assert "expected_behavior" not in text
    assert "reference_solution" not in text
    assert "evaluation_criteria" not in text

    # The publish-readiness/quality-validation payload must not leak
    # criterion content either — messages are static per check, never
    # interpolated with the criterion's own field values.
    readiness_text = client.get(f"/api/v1/quests/{quest['id']}/publish-readiness").text
    for secret in (
        "SECRET_6B_EXPECTED_ANSWER",
        "SECRET_6B_EXPECTED_BEHAVIOR",
        "SECRET_6B_REFERENCE_SOLUTION",
    ):
        assert secret not in readiness_text


# =====================================================================
# 22: publish endpoint revalidates independently — never trusts the
# frontend to have called /publish-readiness first
# =====================================================================


def test_publish_endpoint_revalidates_without_ever_checking_readiness_first(client, demo_employee_id, capability_id):
    """No call to GET /publish-readiness happens anywhere in this test —
    POST /publish must still independently enforce every rule."""
    quest = _new_quest(client, "TROUBLESHOOT", "FIX", title="Publish without checking readiness first")
    res = _publish(client, quest["id"])
    assert res.status_code == 409, res.text

    _add_task(client, quest["id"], "INVESTIGATE")
    _add_evidence(client, quest["id"])
    _add_criterion(client, quest["id"], criterion_type="DETERMINISTIC", expected_answer="answer")
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    res = _publish(client, quest["id"])
    assert res.status_code == 200, res.text


# =====================================================================
# Cross-quest isolation
# =====================================================================


def test_quality_validation_is_isolated_per_quest(client, demo_employee_id, capability_id):
    quest_a = _new_quest(client, "TROUBLESHOOT", "FIX", title="Isolation quest A")
    quest_b = _new_quest(client, "TROUBLESHOOT", "FIX", title="Isolation quest B")

    _add_task(client, quest_a["id"], "INVESTIGATE")
    _add_evidence(client, quest_a["id"])
    _add_criterion(client, quest_a["id"], criterion_type="DETERMINISTIC", expected_answer="answer")
    _map_capability(client, quest_a["id"], capability_id)
    _assign(client, quest_a["id"], demo_employee_id)

    # Quest B has none of quest A's content — must still be fully unready.
    body_b = _readiness(client, quest_b["id"])
    assert body_b["ready"] is False
    assert _error_codes(body_b) >= {
        "MISSING_INVESTIGATION_TASK",
        "MISSING_EVIDENCE",
        "MISSING_EVALUATION",
        "MISSING_CAPABILITY",
        "MISSING_ASSIGNMENT",
    }
    assert _readiness(client, quest_a["id"])["ready"] is True

    assert _publish(client, quest_a["id"]).status_code == 200
    assert _publish(client, quest_b["id"]).status_code == 409

    # Publishing quest A must not have touched quest B's own tasks list.
    assert client.get(f"/api/v1/quests/{quest_b['id']}/tasks").json() == []


# =====================================================================
# Concurrency
# =====================================================================


def test_concurrent_publish_attempts_produce_exactly_one_success(client, demo_employee_id, capability_id):
    quest = _new_quest(client, "TROUBLESHOOT", "FIX", title="Concurrent publish attempts")
    _add_task(client, quest["id"], "INVESTIGATE")
    _add_evidence(client, quest["id"])
    _add_criterion(client, quest["id"], criterion_type="DETERMINISTIC", expected_answer="answer")
    _map_capability(client, quest["id"], capability_id)
    _assign(client, quest["id"], demo_employee_id)

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: _publish(client, quest["id"]), range(8)))

    statuses = [r.status_code for r in responses]
    assert statuses.count(200) == 1, statuses
    assert all(s in (200, 409) for s in statuses)

    final = client.get(f"/api/v1/quests/{quest['id']}").json()
    assert final["status"] == "PUBLISHED"

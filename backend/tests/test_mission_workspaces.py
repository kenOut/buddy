"""Backend tests for the three Mission workspace types (Mission.workspace_type)
and their evaluation paths — this is the codebase's answer to "every
mission gets a real work environment, evaluated live":

  - investigation: unchanged (mission_scenarios.py) — covered exhaustively
    by test_mission_attempts.py already.
  - quiz: deterministic multi-question grading (mission_quizzes.py), no
    AI step (see Mission.workspace_type's own docstring).
  - reflection: freeform submission gated on a real-effort length bar
    (mission_attempt_service._grade_reflection), then a live read from
    the same mock AI provider Quests and investigation Missions already
    use (ai_evaluation_service.evaluate_attempt).

This file covers what test_mission_attempts.py/test_mission_readiness.py
don't: the quiz content endpoint never leaking answers, the AI-evaluate
endpoint actually working end to end for a reflection mission, that same
endpoint correctly refusing a quiz mission (409, nothing to evaluate),
and that both quiz and reflection completions produce real, traceable
CapabilityEvidence rows.

Runs against its own isolated SQLite file, same convention as the other
test_*.py modules.
"""

import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_mission_workspaces.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services import mission_quizzes  # noqa: E402

REFLECTION_TITLE = "Meet your onboarding buddy"
QUIZ_TITLE = "Read the on-call handbook"
QUIZ_ANSWERS = {
    "q1": "Acknowledge the page and start reading the runbook linked in the alert",
    "q2": "Sev-1 is customer-facing and actively losing money or data; Sev-3 is degraded but contained",
    "q3": "If you haven't made progress within the escalation window, or the incident is outside your area",
}


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
def demo_bundle(client):
    return client.get("/api/v1/onboarding/bundle/demo").json()


def _mission_id(bundle, title):
    return next(a for a in bundle["mission_assignments"] if a["mission"]["title"] == title)["mission_id"]


# seed_data.py no longer seeds any demo Missions (see its own module
# docstring), so this file creates the exact 2 titled missions it needs
# itself — titles matter, not just workspace_type, since
# mission_quizzes.py keys its quiz content by exact mission title.
@pytest.fixture(scope="module")
def reflection_mission_id(client, demo_bundle):
    res = client.post(
        "/api/v1/missions",
        json={
            "department_id": demo_bundle["employee"]["department_id"],
            "title": REFLECTION_TITLE,
            "mission_type": "task",
            "workspace_type": "reflection",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


@pytest.fixture(scope="module")
def quiz_mission_id(client, demo_bundle):
    res = client.post(
        "/api/v1/missions",
        json={
            "department_id": demo_bundle["employee"]["department_id"],
            "title": QUIZ_TITLE,
            "mission_type": "task",
            "workspace_type": "quiz",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


@pytest.fixture(scope="module")
def demo_employee_id(client, demo_bundle, reflection_mission_id, quiz_mission_id):
    # A freshly-created employee, not the literal seeded demo identity —
    # P2's Provisioning Boundary means mission assignments are only ever
    # provisioned once, at an employee's first bundle fetch; the real
    # demo employee's session was already created (by `demo_bundle`
    # above) before these missions existed. Depending on both mission
    # fixtures forces them to exist before this employee's first bundle
    # fetch below. Named `demo_employee_id` (not renamed) purely so the
    # two tests using it below keep working unchanged.
    res = client.post(
        "/api/v1/employees",
        json={
            "organization_id": demo_bundle["employee"]["organization_id"],
            "department_id": demo_bundle["employee"]["department_id"],
            "full_name": "Mission Workspaces Demo Test Employee",
            "email": "mission-workspaces-demo-test@kowri.test",
        },
    )
    assert res.status_code == 201, res.text
    employee_id = res.json()["id"]
    client.get(f"/api/v1/onboarding/bundle/{employee_id}")  # provisions assignments
    return employee_id


# =====================================================================
# Quiz content endpoint — never leaks the answer key
# =====================================================================


def test_quiz_endpoint_returns_questions_without_answers(client, quiz_mission_id, demo_employee_id):
    res = client.get(f"/api/v1/missions/{quiz_mission_id}/quiz?employee_id={demo_employee_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["mission_id"] == quiz_mission_id
    assert len(body["questions"]) == 3
    for question in body["questions"]:
        assert set(question.keys()) == {"id", "prompt", "options"}
        assert len(question["options"]) >= 2


def test_quiz_endpoint_404s_for_a_non_quiz_mission(client, reflection_mission_id, demo_employee_id):
    res = client.get(f"/api/v1/missions/{reflection_mission_id}/quiz?employee_id={demo_employee_id}")
    assert res.status_code == 404


def test_quiz_endpoint_403s_for_an_unassigned_employee(client, quiz_mission_id, demo_bundle):
    other = client.post(
        "/api/v1/employees",
        json={
            "organization_id": demo_bundle["employee"]["organization_id"],
            "full_name": "No Department Employee",
            "email": "no-department-quiz@kowri.test",
        },
    ).json()
    res = client.get(f"/api/v1/missions/{quiz_mission_id}/quiz?employee_id={other['id']}")
    assert res.status_code == 403


# =====================================================================
# mission_quizzes.grade — unit-level
# =====================================================================


def test_quiz_grading_partial_credit_still_fails():
    answers = {**QUIZ_ANSWERS, "q3": "wrong"}
    result = mission_quizzes.grade(QUIZ_TITLE, answers)
    assert result.passed is False
    assert result.correct_count == 2
    assert result.total == 3
    assert result.incorrect_question_ids == ["q3"]


def test_quiz_grading_all_correct_passes():
    result = mission_quizzes.grade(QUIZ_TITLE, QUIZ_ANSWERS)
    assert result.passed is True
    assert result.score == 100.0
    assert result.incorrect_question_ids == []


# =====================================================================
# AI evaluation — reflection gets a live read, quiz explicitly does not
# =====================================================================


def _new_employee(client, demo_bundle, *, email):
    return client.post(
        "/api/v1/employees",
        json={
            "organization_id": demo_bundle["employee"]["organization_id"],
            "department_id": demo_bundle["employee"]["department_id"],
            "full_name": "Workspace Test Employee",
            "email": email,
        },
    ).json()


def test_reflection_mission_gets_a_live_ai_evaluation(client, demo_bundle):
    employee = _new_employee(client, demo_bundle, email="ai-eval-reflection@kowri.test")
    bundle = client.get(f"/api/v1/onboarding/bundle/{employee['id']}").json()
    mission_id = _mission_id(bundle, REFLECTION_TITLE)

    attempt = client.post(
        "/api/v1/mission-attempts", json={"mission_id": mission_id, "employee_id": employee["id"]}
    ).json()
    submit = client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/submit",
        json={
            "employee_id": employee["id"],
            "reasoning": "We talked through the on-call rotation, how sprint planning works, and "
            "what tools the team uses day to day.",
        },
    )
    assert submit.json()["passed"] is True

    evaluate = client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/evaluate", json={"employee_id": employee["id"]}
    )
    assert evaluate.status_code == 200, evaluate.text
    body = evaluate.json()
    result = body["structured_result"]
    assert result["summary"]
    capability_keys = {c["capability"] for c in result["capabilities"]}
    # communication/independence — never troubleshooting, which has no
    # basis in a reflection submission (see ai_provider.py's
    # _generate_for_reflection docstring).
    assert capability_keys <= {"communication", "independence"}
    assert "troubleshooting" not in capability_keys

    evidence = client.get(
        f"/api/v1/employees/{employee['id']}/capabilities/evidence"
    ).json()
    sources = {e["source"] for e in evidence}
    assert "deterministic" in sources
    assert "ai" in sources


def test_quiz_mission_has_no_ai_evaluation_step(client, demo_bundle):
    employee = _new_employee(client, demo_bundle, email="ai-eval-quiz@kowri.test")
    bundle = client.get(f"/api/v1/onboarding/bundle/{employee['id']}").json()
    mission_id = _mission_id(bundle, QUIZ_TITLE)

    attempt = client.post(
        "/api/v1/mission-attempts", json={"mission_id": mission_id, "employee_id": employee["id"]}
    ).json()
    submit = client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/submit",
        json={"employee_id": employee["id"], "quiz_answers": QUIZ_ANSWERS},
    )
    assert submit.json()["passed"] is True

    evaluate = client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/evaluate", json={"employee_id": employee["id"]}
    )
    assert evaluate.status_code == 409

    # The deterministic quiz_passed evidence still exists even with no AI step.
    evidence = client.get(f"/api/v1/employees/{employee['id']}/capabilities/evidence").json()
    sources = {e["source"] for e in evidence}
    assert "deterministic" in sources
    assert "ai" not in sources


def test_evaluate_requires_a_completed_attempt(client, demo_bundle):
    employee = _new_employee(client, demo_bundle, email="ai-eval-incomplete@kowri.test")
    bundle = client.get(f"/api/v1/onboarding/bundle/{employee['id']}").json()
    mission_id = _mission_id(bundle, REFLECTION_TITLE)

    attempt = client.post(
        "/api/v1/mission-attempts", json={"mission_id": mission_id, "employee_id": employee["id"]}
    ).json()
    # Never submitted — still not_started/in_progress.
    res = client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/evaluate", json={"employee_id": employee["id"]}
    )
    assert res.status_code == 409

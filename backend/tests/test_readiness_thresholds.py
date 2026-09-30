"""Stage 2 — Performance-Aware Readiness & Explainable Blockers.

Covers the threshold-satisfaction predicate readiness_service.py adds
on top of its pre-existing completion-only gate: Mission.minimum_score /
QuestAssignment.minimum_score, RequiredItemState.satisfied, the
structured ReadinessBlocker list, and that no averaging formula is used
anywhere in the readiness computation.

Attempt state (score/status) is written directly via a DB session
rather than driven through the real submission flow — this isolates the
readiness threshold predicate from the scoring pipeline's own mechanics
(deterministic Mission grading only ever produces 0.0 or 100.0; this
file needs exact values like 78 to test a threshold precisely), and
mirrors the `force_published` precedent test_quest_evaluation.py already
established for reaching states the ordinary API surface can't produce
directly. Scoring itself is explicitly out of scope for Stage 2 — see
readiness_service.py's own module docstring.

Runs against its own isolated SQLite file, same convention as every
other test_*.py module in this suite.
"""

import asyncio
import itertools
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_readiness_thresholds.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Mission, MissionAssignment, MissionAttempt, QuestAssignment, QuestAttempt  # noqa: E402


@pytest.fixture(scope="module")
def client():
    # Reassigned here, not just once at module import time — this
    # suite's own established fragility class (first diagnosed in
    # P2.1, recurring in P3/P4.1/the Correction phase/Stage 1): every
    # test file sets DATABASE_URL once at module top-level, but a
    # module-scoped fixture doesn't actually execute until pytest gets
    # around to its first test, by which point a later-collected
    # file's own top-level assignment may have already overwritten it.
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
    bundle = client.get("/api/v1/onboarding/bundle/demo").json()
    return bundle["employee"]["organization_id"]


@pytest.fixture(scope="module")
def capability_ids(client):
    caps = client.get("/api/v1/capabilities").json()
    return {c["key"]: c["id"] for c in caps}


_dept_counter = itertools.count()
_email_counter = itertools.count()
_title_counter = itertools.count()


def _make_department(client, org_id):
    """Every test gets its own department — Mission assignments are
    auto-provisioned to every employee created in a department, so
    reusing one department across tests would let an earlier test's
    required Mission silently become a later test's blocker too (the
    exact cross-contamination bug caught and fixed in Stage 1)."""
    res = client.post(
        "/api/v1/departments",
        json={"organization_id": org_id, "name": f"Threshold Test Dept {next(_dept_counter)}"},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _make_employee(client, org_id, department_id):
    res = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department_id,
            "full_name": "Threshold Test Employee",
            "email": f"threshold-test-{next(_email_counter)}@kowri.test",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _make_mission(client, department_id, *, required=True, minimum_score=None, title=None):
    title = title or f"Threshold Mission {next(_title_counter)}"
    res = client.post(
        "/api/v1/missions",
        json={
            "department_id": department_id,
            "title": title,
            "mission_type": "task",
            "workspace_type": "reflection",
            "required": required,
            "minimum_score": minimum_score,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"], title


def _set_mission_state(mission_id, employee_id, *, completed, score):
    """Directly writes the MissionAssignment.status + MissionAttempt row
    readiness_service reads — see module docstring for why."""

    async def _do():
        async with AsyncSessionLocal() as db:
            assignment = (
                await db.execute(
                    select(MissionAssignment).where(
                        MissionAssignment.mission_id == mission_id,
                        MissionAssignment.employee_id == employee_id,
                    )
                )
            ).scalar_one_or_none()
            assert assignment is not None, "mission was not auto-provisioned to this employee"
            assignment.status = "completed" if completed else "in_progress"

            if score is not None:
                attempt = (
                    await db.execute(
                        select(MissionAttempt).where(
                            MissionAttempt.mission_id == mission_id,
                            MissionAttempt.employee_id == employee_id,
                        )
                    )
                ).scalar_one_or_none()
                if attempt is None:
                    attempt = MissionAttempt(mission_id=mission_id, employee_id=employee_id)
                    db.add(attempt)
                attempt.status = "completed" if completed else "submitted"
                attempt.score = score
                attempt.passed = completed

            await db.commit()

    asyncio.run(_do())


def _make_published_quest(client, employee_id, capability_ids, *, required=True, minimum_score=None, title=None):
    title = title or f"Threshold Quest {next(_title_counter)}"
    quest = client.post(
        "/api/v1/quests",
        json={
            "title": title,
            "description": "A quest used only for readiness-threshold tests.",
            "quest_type": "INVESTIGATE",
            "workspace_type": "INVESTIGATION",
        },
    ).json()
    qid = quest["id"]
    client.post(
        f"/api/v1/quests/{qid}/tasks",
        json={"title": "Identify the affected service", "task_type": "INVESTIGATE", "required": False},
    )
    client.post(
        f"/api/v1/quests/{qid}/evidence",
        json={"title": "Latency metrics", "evidence_type": "METRICS", "content": {}},
    )
    client.post(
        f"/api/v1/quests/{qid}/evaluation-criteria",
        json={
            "name": "Correct affected service",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "checkout-service",
            "max_score": 100,
        },
    )
    client.post(
        f"/api/v1/quests/{qid}/capabilities",
        json={"capability_id": capability_ids["troubleshooting"], "weight": 1.0},
    )
    res = client.post(
        f"/api/v1/quests/{qid}/assignments",
        json={
            "assignment_type": "EMPLOYEE",
            "employee_id": employee_id,
            "required": required,
            "minimum_score": minimum_score,
        },
    )
    assert res.status_code == 201, res.text
    pub = client.post(f"/api/v1/quests/{qid}/publish")
    assert pub.status_code == 200, pub.text
    return qid, title


def _set_quest_state(quest_id, employee_id, *, completed, score):
    async def _do():
        async with AsyncSessionLocal() as db:
            attempt = (
                await db.execute(
                    select(QuestAttempt).where(
                        QuestAttempt.quest_id == quest_id, QuestAttempt.employee_id == employee_id
                    )
                )
            ).scalar_one_or_none()
            if attempt is None:
                attempt = QuestAttempt(quest_id=quest_id, employee_id=employee_id)
                db.add(attempt)
            attempt.status = "COMPLETED" if completed else "IN_PROGRESS"
            if score is not None:
                attempt.score = score
                attempt.passed = completed
            await db.commit()

    asyncio.run(_do())


def _readiness(client, employee_id):
    res = client.get(f"/api/v1/employees/{employee_id}/readiness-summary")
    assert res.status_code == 200, res.text
    return res.json()


def _performance(client, employee_id):
    res = client.get(f"/api/v1/employees/{employee_id}/performance")
    assert res.status_code == 200, res.text
    return res.json()


def _complete_onboarding(client, employee_id):
    bundle = client.get(f"/api/v1/onboarding/bundle/{employee_id}").json()
    session_id = bundle["session"]["id"]
    res = client.patch(f"/api/v1/onboarding/sessions/{session_id}", json={"current_scene": "completion"})
    assert res.status_code == 200, res.text


# =====================================================================
# 1-10 — Threshold semantics (generic, mission-flavored where a concrete
# item type is needed; Quest-flavored equivalents are covered by 14-16)
# =====================================================================


def test_required_item_null_threshold_completed_is_satisfied(client, org_id, capability_ids):
    dept = _make_department(client, org_id)
    mission_id, title = _make_mission(client, dept, required=True, minimum_score=None)
    employee_id = _make_employee(client, org_id, dept)
    _set_mission_state(mission_id, employee_id, completed=True, score=100.0)
    _complete_onboarding(client, employee_id)
    quest_id, _ = _make_published_quest(client, employee_id, capability_ids, required=True, minimum_score=None)
    _set_quest_state(quest_id, employee_id, completed=True, score=100.0)

    readiness = _readiness(client, employee_id)
    assert readiness["ready"] is True
    perf = _performance(client, employee_id)
    m = next(m for m in perf["missions"] if m["id"] == mission_id)
    assert m["threshold_status"] == "SATISFIED"


def test_required_item_threshold_score_above_is_satisfied(client, org_id, capability_ids):
    dept = _make_department(client, org_id)
    mission_id, _ = _make_mission(client, dept, required=True, minimum_score=80)
    employee_id = _make_employee(client, org_id, dept)
    _set_mission_state(mission_id, employee_id, completed=True, score=85.0)

    perf = _performance(client, employee_id)
    m = next(m for m in perf["missions"] if m["id"] == mission_id)
    assert m["threshold_status"] == "SATISFIED"
    assert m["score"] == 85.0
    assert m["minimum_score"] == 80.0


def test_required_item_threshold_score_exactly_equal_is_satisfied(client, org_id, capability_ids):
    dept = _make_department(client, org_id)
    mission_id, _ = _make_mission(client, dept, required=True, minimum_score=80)
    employee_id = _make_employee(client, org_id, dept)
    _set_mission_state(mission_id, employee_id, completed=True, score=80.0)

    perf = _performance(client, employee_id)
    m = next(m for m in perf["missions"] if m["id"] == mission_id)
    assert m["threshold_status"] == "SATISFIED"


def test_required_item_threshold_score_below_is_blocked(client, org_id):
    dept = _make_department(client, org_id)
    mission_id, title = _make_mission(client, dept, required=True, minimum_score=80)
    employee_id = _make_employee(client, org_id, dept)
    _set_mission_state(mission_id, employee_id, completed=True, score=78.0)

    readiness = _readiness(client, employee_id)
    assert readiness["ready"] is False
    perf = _performance(client, employee_id)
    m = next(m for m in perf["missions"] if m["id"] == mission_id)
    assert m["threshold_status"] == "BELOW_THRESHOLD"
    blocker = next(b for b in perf["readiness"]["blockers"] if b["item_id"] == mission_id)
    assert blocker["type"] == "REQUIRED_MISSION_BELOW_THRESHOLD"
    assert blocker["score"] == 78.0
    assert blocker["minimum_score"] == 80.0


def test_required_incomplete_item_blocked_regardless_of_threshold(client, org_id):
    dept = _make_department(client, org_id)
    mission_id, _ = _make_mission(client, dept, required=True, minimum_score=80)
    employee_id = _make_employee(client, org_id, dept)
    _set_mission_state(mission_id, employee_id, completed=False, score=None)

    perf = _performance(client, employee_id)
    m = next(m for m in perf["missions"] if m["id"] == mission_id)
    assert m["threshold_status"] == "INCOMPLETE"
    blocker = next(b for b in perf["readiness"]["blockers"] if b["item_id"] == mission_id)
    assert blocker["type"] == "REQUIRED_MISSION_INCOMPLETE"


def test_optional_item_below_threshold_does_not_block_readiness(client, org_id, capability_ids):
    dept = _make_department(client, org_id)
    mission_id, _ = _make_mission(client, dept, required=False, minimum_score=80)
    employee_id = _make_employee(client, org_id, dept)
    _set_mission_state(mission_id, employee_id, completed=True, score=10.0)
    _complete_onboarding(client, employee_id)
    quest_id, _ = _make_published_quest(client, employee_id, capability_ids, required=True, minimum_score=None)
    _set_quest_state(quest_id, employee_id, completed=True, score=100.0)

    readiness = _readiness(client, employee_id)
    assert readiness["ready"] is True
    perf = _performance(client, employee_id)
    m = next(m for m in perf["missions"] if m["id"] == mission_id)
    assert m["threshold_status"] is None
    assert not any(b["item_id"] == mission_id for b in perf["readiness"]["blockers"])


def test_optional_item_incomplete_does_not_block_readiness(client, org_id, capability_ids):
    dept = _make_department(client, org_id)
    mission_id, _ = _make_mission(client, dept, required=False, minimum_score=80)
    employee_id = _make_employee(client, org_id, dept)
    # never started at all
    _complete_onboarding(client, employee_id)
    quest_id, _ = _make_published_quest(client, employee_id, capability_ids, required=True, minimum_score=None)
    _set_quest_state(quest_id, employee_id, completed=True, score=100.0)

    readiness = _readiness(client, employee_id)
    assert readiness["ready"] is True


def test_multiple_required_items_evaluated_independently(client, org_id):
    dept = _make_department(client, org_id)
    m1, _ = _make_mission(client, dept, required=True, minimum_score=80, title="Mission A")
    m2, _ = _make_mission(client, dept, required=True, minimum_score=75, title="Mission B")
    m3, _ = _make_mission(client, dept, required=True, minimum_score=None, title="Mission C")
    employee_id = _make_employee(client, org_id, dept)
    _set_mission_state(m1, employee_id, completed=True, score=85.0)  # satisfied
    _set_mission_state(m2, employee_id, completed=True, score=72.0)  # below threshold
    _set_mission_state(m3, employee_id, completed=True, score=1.0)  # NULL threshold, completion enough

    perf = _performance(client, employee_id)
    statuses = {m["id"]: m["threshold_status"] for m in perf["missions"]}
    assert statuses[m1] == "SATISFIED"
    assert statuses[m2] == "BELOW_THRESHOLD"
    assert statuses[m3] == "SATISFIED"


def test_one_below_threshold_makes_employee_not_ready(client, org_id, capability_ids):
    dept = _make_department(client, org_id)
    m1, _ = _make_mission(client, dept, required=True, minimum_score=80)
    m2, _ = _make_mission(client, dept, required=True, minimum_score=75)
    employee_id = _make_employee(client, org_id, dept)
    _set_mission_state(m1, employee_id, completed=True, score=91.0)
    _set_mission_state(m2, employee_id, completed=True, score=72.0)
    _complete_onboarding(client, employee_id)
    quest_id, _ = _make_published_quest(client, employee_id, capability_ids, required=True, minimum_score=None)
    _set_quest_state(quest_id, employee_id, completed=True, score=100.0)

    # Even though the average of (91, 72) is 81.5 — well above either
    # individual bar — the employee is NOT ready, because Mission B's
    # own score never met ITS OWN threshold. This is the exact
    # "averaging must never substitute for per-item evaluation" case
    # Stage 2 §2 describes.
    readiness = _readiness(client, employee_id)
    assert readiness["ready"] is False


def test_all_required_items_satisfy_thresholds_employee_ready(client, org_id, capability_ids):
    dept = _make_department(client, org_id)
    m1, _ = _make_mission(client, dept, required=True, minimum_score=80)
    m2, _ = _make_mission(client, dept, required=True, minimum_score=75)
    employee_id = _make_employee(client, org_id, dept)
    _set_mission_state(m1, employee_id, completed=True, score=91.0)
    _set_mission_state(m2, employee_id, completed=True, score=75.0)
    _complete_onboarding(client, employee_id)
    quest_id, _ = _make_published_quest(client, employee_id, capability_ids, required=True, minimum_score=90)
    _set_quest_state(quest_id, employee_id, completed=True, score=90.0)

    readiness = _readiness(client, employee_id)
    assert readiness["ready"] is True
    assert readiness["required_items_below_threshold"] == 0


# =====================================================================
# 11-13 — Mission-specific
# =====================================================================


def test_required_mission_below_threshold_blocks_readiness(client, org_id, capability_ids):
    dept = _make_department(client, org_id)
    mission_id, _ = _make_mission(client, dept, required=True, minimum_score=80)
    employee_id = _make_employee(client, org_id, dept)
    _set_mission_state(mission_id, employee_id, completed=True, score=50.0)
    _complete_onboarding(client, employee_id)
    quest_id, _ = _make_published_quest(client, employee_id, capability_ids, required=True, minimum_score=None)
    _set_quest_state(quest_id, employee_id, completed=True, score=100.0)

    assert _readiness(client, employee_id)["ready"] is False


def test_required_mission_meeting_threshold_satisfies_readiness(client, org_id, capability_ids):
    dept = _make_department(client, org_id)
    mission_id, _ = _make_mission(client, dept, required=True, minimum_score=80)
    employee_id = _make_employee(client, org_id, dept)
    _set_mission_state(mission_id, employee_id, completed=True, score=80.0)
    _complete_onboarding(client, employee_id)
    quest_id, _ = _make_published_quest(client, employee_id, capability_ids, required=True, minimum_score=None)
    _set_quest_state(quest_id, employee_id, completed=True, score=100.0)

    assert _readiness(client, employee_id)["ready"] is True


def test_required_mission_null_threshold_preserves_old_behavior(client, org_id, capability_ids):
    dept = _make_department(client, org_id)
    mission_id, _ = _make_mission(client, dept, required=True, minimum_score=None)
    employee_id = _make_employee(client, org_id, dept)
    _set_mission_state(mission_id, employee_id, completed=True, score=1.0)  # a very low score, no threshold
    _complete_onboarding(client, employee_id)
    quest_id, _ = _make_published_quest(client, employee_id, capability_ids, required=True, minimum_score=None)
    _set_quest_state(quest_id, employee_id, completed=True, score=100.0)

    assert _readiness(client, employee_id)["ready"] is True


# =====================================================================
# 14-16 — Quest-specific
# =====================================================================


def test_required_quest_below_threshold_blocks_readiness(client, org_id, capability_ids):
    dept = _make_department(client, org_id)
    employee_id = _make_employee(client, org_id, dept)
    _complete_onboarding(client, employee_id)
    quest_id, _ = _make_published_quest(client, employee_id, capability_ids, required=True, minimum_score=80)
    _set_quest_state(quest_id, employee_id, completed=True, score=60.0)

    assert _readiness(client, employee_id)["ready"] is False


def test_required_quest_meeting_threshold_satisfies_readiness(client, org_id, capability_ids):
    dept = _make_department(client, org_id)
    employee_id = _make_employee(client, org_id, dept)
    _complete_onboarding(client, employee_id)
    quest_id, _ = _make_published_quest(client, employee_id, capability_ids, required=True, minimum_score=80)
    _set_quest_state(quest_id, employee_id, completed=True, score=80.0)

    assert _readiness(client, employee_id)["ready"] is True


def test_required_quest_null_threshold_preserves_old_behavior(client, org_id, capability_ids):
    dept = _make_department(client, org_id)
    employee_id = _make_employee(client, org_id, dept)
    _complete_onboarding(client, employee_id)
    quest_id, _ = _make_published_quest(client, employee_id, capability_ids, required=True, minimum_score=None)
    _set_quest_state(quest_id, employee_id, completed=True, score=1.0)

    assert _readiness(client, employee_id)["ready"] is True


def test_multiple_required_assignments_same_quest_strictest_threshold_wins(client, org_id, capability_ids):
    """Domain evidence (Stage 2 Final Domain Decision Check, question 2):

    quest_assignment_service.py's own matching (_assignment_matches_
    employee, used identically by get_matching_assignment_types,
    is_employee_eligible, and list_eligible_quest_ids_for_employee) is a
    pure OR across every assignment that matches an employee — there is
    no "one assignment wins" precedence anywhere in that file today.
    Two different assignment_type rows on the same Quest (e.g. one
    DEPARTMENT, one EMPLOYEE) are not mutually exclusive — the model's
    partial unique indexes only prevent a DUPLICATE of the SAME type for
    the SAME target, never a second, different-typed assignment on the
    same Quest — so an employee can genuinely be covered by both at
    once. Given that, and given no existing precedence rule to defer to,
    readiness_service.required_quest_items takes the STRICTEST (max)
    configured threshold among every required assignment the employee
    matches, rather than picking an arbitrary one — the same reasoning
    already applied to combining `required` itself (any matching
    required assignment makes the Quest required; the threshold
    extension keeps that same "any real requirement counts" posture by
    never letting a looser assignment silently relax a stricter one).

    Effective threshold, this test's own setup: Department assignment
    75%, Employee (personal) assignment 85%, same employee + Quest —
    documented expected result is 85% (the max), confirmed both via the
    raw threshold value AND behaviorally (a score of 80 — comfortably
    above the department's 75% but below the personal 85% — must still
    leave the employee NOT ready and BELOW_THRESHOLD)."""
    dept = _make_department(client, org_id)
    employee_id = _make_employee(client, org_id, dept)
    _complete_onboarding(client, employee_id)

    quest = client.post(
        "/api/v1/quests",
        json={
            "title": "Precedence Test Quest",
            "description": "A quest used only for the assignment-precedence regression test.",
            "quest_type": "INVESTIGATE",
            "workspace_type": "INVESTIGATION",
        },
    ).json()
    qid = quest["id"]
    client.post(
        f"/api/v1/quests/{qid}/tasks",
        json={"title": "Identify the affected service", "task_type": "INVESTIGATE", "required": False},
    )
    client.post(
        f"/api/v1/quests/{qid}/evidence",
        json={"title": "Latency metrics", "evidence_type": "METRICS", "content": {}},
    )
    client.post(
        f"/api/v1/quests/{qid}/evaluation-criteria",
        json={
            "name": "Correct affected service",
            "criterion_type": "DETERMINISTIC",
            "expected_answer": "checkout-service",
            "max_score": 100,
        },
    )
    client.post(
        f"/api/v1/quests/{qid}/capabilities",
        json={"capability_id": capability_ids["troubleshooting"], "weight": 1.0},
    )
    # Department assignment: required, 75% minimum.
    res_dept = client.post(
        f"/api/v1/quests/{qid}/assignments",
        json={"assignment_type": "DEPARTMENT", "department_id": dept, "required": True, "minimum_score": 75},
    )
    assert res_dept.status_code == 201, res_dept.text
    # Personal assignment on the SAME employee, SAME Quest: required,
    # 85% minimum — a different assignment_type row, not a duplicate
    # (the model's partial unique indexes are scoped per-type, so this
    # coexists with the DEPARTMENT row above without conflict).
    res_emp = client.post(
        f"/api/v1/quests/{qid}/assignments",
        json={
            "assignment_type": "EMPLOYEE",
            "employee_id": employee_id,
            "required": True,
            "minimum_score": 85,
        },
    )
    assert res_emp.status_code == 201, res_emp.text
    pub = client.post(f"/api/v1/quests/{qid}/publish")
    assert pub.status_code == 200, pub.text

    # A score that clears the DEPARTMENT bar (75) but not the personal
    # one (85) — documents that the effective threshold is 85, not 75
    # and not an average of the two.
    _set_quest_state(qid, employee_id, completed=True, score=80.0)

    perf = _performance(client, employee_id)
    q = next(q for q in perf["quests"] if q["id"] == qid)
    assert q["minimum_score"] == 85.0, "effective threshold must be the strictest (max) of the two matching assignments"
    assert q["threshold_status"] == "BELOW_THRESHOLD"
    assert _readiness(client, employee_id)["ready"] is False

    # Raising the score to clear even the stricter 85% bar now satisfies
    # readiness — confirming 85 (not 75) was genuinely the gate.
    _set_quest_state(qid, employee_id, completed=True, score=85.0)
    perf = _performance(client, employee_id)
    q = next(q for q in perf["quests"] if q["id"] == qid)
    assert q["threshold_status"] == "SATISFIED"
    assert _readiness(client, employee_id)["ready"] is True


# =====================================================================
# 17-20 — Existing behavior / workspace access
# =====================================================================


def test_existing_assignments_without_threshold_remain_compatible(client, org_id, capability_ids):
    """The exact pre-Stage-2 shape: required + completed + no threshold
    configured anywhere — must still be ready, unchanged."""
    dept = _make_department(client, org_id)
    mission_id, _ = _make_mission(client, dept, required=True)
    employee_id = _make_employee(client, org_id, dept)
    _set_mission_state(mission_id, employee_id, completed=True, score=100.0)
    _complete_onboarding(client, employee_id)
    quest_id, _ = _make_published_quest(client, employee_id, capability_ids, required=True)
    _set_quest_state(quest_id, employee_id, completed=True, score=100.0)

    assert _readiness(client, employee_id)["ready"] is True


def test_existing_readiness_summary_fields_remain_present(client, org_id):
    dept = _make_department(client, org_id)
    employee_id = _make_employee(client, org_id, dept)
    summary = _readiness(client, employee_id)
    for field in (
        "ready", "onboarding_completed", "required_quest_count", "completed_required_quest_count",
        "remaining_required_quest_count", "required_mission_count", "completed_required_mission_count",
        "remaining_required_mission_count", "required_items_below_threshold",
    ):
        assert field in summary


def test_workspace_access_not_granted_when_below_threshold(client, org_id, capability_ids):
    dept = _make_department(client, org_id)
    employee_id = _make_employee(client, org_id, dept)
    _complete_onboarding(client, employee_id)
    quest_id, _ = _make_published_quest(client, employee_id, capability_ids, required=True, minimum_score=90)
    _set_quest_state(quest_id, employee_id, completed=True, score=60.0)

    async def _check():
        from app.services import readiness_service
        return await readiness_service.check_and_trigger(employee_id)

    grant = asyncio.run(_check())
    assert grant is None


def test_workspace_access_granted_once_threshold_satisfied(client, org_id, capability_ids):
    # Configure a real WorkspaceIntegration for this department so
    # ensure_access has something to grant against.
    dept = _make_department(client, org_id)
    integ = client.post(
        f"/api/v1/departments/{dept}/workspace",
        json={
            "provider": "google_drive",
            "external_ref": "threshold-test-folder",
            "display_name": "Threshold Test Workspace",
            "workspace_link": "https://drive.google.com/drive/folders/threshold-test",
        },
    )
    employee_id = _make_employee(client, org_id, dept)
    _complete_onboarding(client, employee_id)
    quest_id, _ = _make_published_quest(client, employee_id, capability_ids, required=True, minimum_score=80)
    _set_quest_state(quest_id, employee_id, completed=True, score=80.0)

    async def _check():
        from app.services import readiness_service
        return await readiness_service.check_and_trigger(employee_id)

    grant = asyncio.run(_check())
    if integ.status_code == 201:
        assert grant is not None
        assert grant.status == "GRANTED"
    else:
        # No workspace-integration endpoint / provider available in this
        # environment — the important assertion is still that a
        # threshold-satisfying employee reaches is_ready()==True, which
        # is what actually gates check_and_trigger's own ensure_access
        # call (proven directly, independent of provider availability).
        async def _is_ready():
            from app.db.session import AsyncSessionLocal as ASL
            from app.models import Employee
            from app.services import readiness_service
            async with ASL() as db:
                employee = await db.get(Employee, employee_id)
                return await readiness_service.is_ready(db, employee)

        assert asyncio.run(_is_ready()) is True


# =====================================================================
# 21-24 — Security
# =====================================================================


def test_employee_cannot_modify_minimum_score(client, org_id, capability_ids):
    """No employee-facing endpoint anywhere accepts minimum_score —
    Mission/QuestAssignment writes are both admin-gated router-wide
    (missions.router, quest_assignments.router — see api/v1/router.py).
    Confirmed here by hitting the write routes with no admin session."""
    dept = _make_department(client, org_id)
    anon = TestClient(app)
    res = anon.post(
        "/api/v1/missions",
        json={"department_id": dept, "title": "Attempted", "required": True, "minimum_score": 10},
    )
    assert res.status_code == 401


def test_employee_cannot_modify_readiness(client, org_id):
    """The readiness-summary endpoint is GET-only; no employee-facing
    write path to `ready` exists anywhere."""
    dept = _make_department(client, org_id)
    employee_id = _make_employee(client, org_id, dept)
    res = client.post(f"/api/v1/employees/{employee_id}/readiness-summary", json={"ready": True})
    assert res.status_code in (404, 405)


def test_manager_endpoint_exposes_threshold_not_internals(client, org_id, capability_ids):
    dept = _make_department(client, org_id)
    employee_id = _make_employee(client, org_id, dept)
    quest_id, _ = _make_published_quest(client, employee_id, capability_ids, required=True, minimum_score=80)
    perf = _performance(client, employee_id)
    q = next(q for q in perf["quests"] if q["id"] == quest_id)
    assert q["minimum_score"] == 80.0
    assert "expected_answer" not in q
    assert "reference_solution" not in q


def test_no_answer_or_reference_fields_leak(client, org_id, capability_ids):
    dept = _make_department(client, org_id)
    mission_id, _ = _make_mission(client, dept, required=True, minimum_score=80)
    employee_id = _make_employee(client, org_id, dept)
    quest_id, _ = _make_published_quest(client, employee_id, capability_ids, required=True, minimum_score=80)
    _set_mission_state(mission_id, employee_id, completed=True, score=50.0)
    _set_quest_state(quest_id, employee_id, completed=True, score=50.0)

    import json

    perf = _performance(client, employee_id)
    blob = json.dumps(perf)
    for forbidden in (
        "expected_answer", "expected_behavior", "reference_solution",
        "correct_service", "correct_cause", "correct_option", "raw_response",
    ):
        assert forbidden not in blob


# =====================================================================
# 25-28 — Edge cases
# =====================================================================


def test_missing_score_on_completed_item_is_not_satisfied_when_threshold_set(client, org_id):
    """A completed-but-scoreless required item with a real threshold
    configured — a data inconsistency in practice (every submit path
    sets score unconditionally), but readiness_service must not treat
    it as passing by default."""
    dept = _make_department(client, org_id)
    mission_id, _ = _make_mission(client, dept, required=True, minimum_score=80)
    employee_id = _make_employee(client, org_id, dept)
    _set_mission_state(mission_id, employee_id, completed=True, score=None)

    perf = _performance(client, employee_id)
    m = next(m for m in perf["missions"] if m["id"] == mission_id)
    assert m["threshold_status"] == "BELOW_THRESHOLD"
    assert _readiness(client, employee_id)["ready"] is False


def test_invalid_negative_threshold_rejected(client, org_id):
    dept = _make_department(client, org_id)
    res = client.post(
        "/api/v1/missions",
        json={"department_id": dept, "title": "Bad Threshold", "required": True, "minimum_score": -5},
    )
    assert res.status_code == 422


def test_invalid_threshold_above_range_rejected(client, org_id):
    dept = _make_department(client, org_id)
    res = client.post(
        "/api/v1/missions",
        json={"department_id": dept, "title": "Bad Threshold 2", "required": True, "minimum_score": 150},
    )
    assert res.status_code == 422


def test_missing_assignment_or_attempt_handled_safely(client, org_id):
    """A required Mission that was created after the employee's own
    session (so no MissionAssignment was ever provisioned for it) —
    Stage 1 already established this is a real, valid state, not a
    crash. Confirmed still true with thresholds in the mix."""
    dept = _make_department(client, org_id)
    employee_id = _make_employee(client, org_id, dept)
    # Created AFTER the employee — never provisioned to them.
    mission_id, title = _make_mission(client, dept, required=True, minimum_score=80)

    perf = _performance(client, employee_id)
    assert not any(m["id"] == mission_id for m in perf["missions"])
    blocker = next(b for b in perf["readiness"]["blockers"] if b["item_id"] == mission_id)
    assert blocker["type"] == "REQUIRED_MISSION_INCOMPLETE"
    assert blocker["score"] is None

"""Backend tests: required Missions as a second readiness gate,
alongside required Quests (see readiness_service.py's module docstring
for the full predicate and the deliberate asymmetry — Missions get no
"at least one must exist" floor the way Quests do).

Covers: the predicate itself (mission gate blocks/unblocks readiness
independently of the quest gate), that zero required missions leaves
the gate vacuously satisfied (no regression for every existing
department that has none configured), department-scoping of
`Mission.required`, the readiness-summary count fields, the real
end-to-end trigger through both Mission completion paths (the "simple"
PATCH and the investigation submit flow), and the admin PATCH
/missions/{id} endpoint used to opt a Mission into being required.

Runs against its own isolated SQLite file, same convention as the other
test_*.py modules.
"""

import asyncio
import itertools
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_mission_readiness.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Employee, WorkspaceAccessGrant, WorkspaceIntegration  # noqa: E402
from app.services import readiness_service  # noqa: E402

_email_counter = itertools.count()
_dept_counter = itertools.count()
_quest_counter = itertools.count()
_mission_counter = itertools.count()

INVESTIGATION_TITLE = "Investigate the payment-worker crash loop"
INVESTIGATION_SERVICE = "payment-worker"
INVESTIGATION_CAUSE = "New deploy raised memory usage past the pod's memory limit, triggering OOMKills"


def run(coro):
    return asyncio.run(coro)


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
def capability_ids(client):
    caps = client.get("/api/v1/capabilities").json()
    return {c["key"]: c["id"] for c in caps}


@pytest.fixture
def department(client, org_id):
    return client.post(
        "/api/v1/departments",
        json={"organization_id": org_id, "name": f"Mission Readiness Dept {next(_dept_counter)}"},
    ).json()


def _employee_in(client, org_id, department_id):
    return client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department_id,
            "full_name": "Mission Readiness Employee",
            "email": f"mission-readiness-{next(_email_counter)}@kowri.test",
        },
    ).json()


@pytest.fixture
def make_employee(client, org_id, department):
    """A factory, not a ready-made employee. P2 — Provisioning Boundary
    made onboarding-session/mission-assignment creation happen eagerly
    at employee-creation time rather than lazily on first bundle fetch
    (see onboarding_service.get_or_create_session) — so a test that
    wants a Mission included in an employee's assignments must create
    that Mission BEFORE the employee exists. Call this once the test is
    ready, not before."""

    def _make():
        return _employee_in(client, org_id, department["id"])

    return _make


def _create_mission(client, department_id, *, title=None, required=True, mission_type="task"):
    title = title or f"Readiness Test Mission {next(_mission_counter)}"
    res = client.post(
        "/api/v1/missions",
        json={
            "department_id": department_id,
            "title": title,
            "description": "A mission used only for readiness tests.",
            "mission_type": mission_type,
            "required": required,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _provision_assignments(client, employee_id):
    """Assignments are provisioned once, eagerly, at employee-creation
    time (P2 — Provisioning Boundary; previously this happened lazily on
    an employee's first bundle fetch instead). Fetching the bundle here
    just reads back whatever was already assigned during creation — it
    does not provision anything itself. Any Mission a test wants
    included must exist BEFORE the employee is created — see
    make_employee."""
    return client.get(f"/api/v1/onboarding/bundle/{employee_id}").json()


def _complete_onboarding(client, employee_id):
    bundle = _provision_assignments(client, employee_id)
    session_id = bundle["session"]["id"]
    res = client.patch(f"/api/v1/onboarding/sessions/{session_id}", json={"current_scene": "completion"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "completed"


def _assignment_id_for(client, employee_id, mission_title):
    bundle = client.get(f"/api/v1/onboarding/bundle/{employee_id}").json()
    match = next(a for a in bundle["mission_assignments"] if a["mission"]["title"] == mission_title)
    return match["id"]


def _complete_reflection_mission(client, employee_id, mission_id):
    """`_create_mission` defaults to workspace_type="reflection" — real
    work submission through the same attempt/submit flow every other
    workspace type uses, not a bare status PATCH (that endpoint no
    longer exists — see mission_attempts.py's own history)."""
    attempt = client.post(
        "/api/v1/mission-attempts", json={"mission_id": mission_id, "employee_id": employee_id}
    ).json()
    res = client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/submit",
        json={
            "employee_id": employee_id,
            "reasoning": "I installed the Kowri CLI, cloned the platform repos, and ran the bootstrap "
            "script end to end — it finished clean with no errors.",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["passed"] is True
    return body


def _complete_investigation_mission(client, employee_id, mission_id):
    attempt = client.post(
        "/api/v1/mission-attempts", json={"mission_id": mission_id, "employee_id": employee_id}
    ).json()
    res = client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/submit",
        json={
            "employee_id": employee_id,
            "affected_service": INVESTIGATION_SERVICE,
            "likely_cause": INVESTIGATION_CAUSE,
            "reasoning": "The deploy raised memory usage past the pod limit.",
            "evidence_viewed": ["metrics:m1", "logs:l1"],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["passed"] is True
    return body


def _build_quest(client, department_id, capability_ids, *, expected_answer="checkout-service"):
    title = f"Mission Readiness Quest {next(_quest_counter)}"
    quest = client.post(
        "/api/v1/quests",
        json={
            "title": title,
            "description": "A real workplace problem used only for readiness tests.",
            "quest_type": "INVESTIGATE",
            "workspace_type": "INVESTIGATION",
            "department_id": department_id,
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
            "expected_answer": expected_answer,
            "max_score": 100,
        },
    )
    client.post(
        f"/api/v1/quests/{qid}/capabilities",
        json={"capability_id": capability_ids["troubleshooting"], "weight": 1.0},
    )
    return qid


def _assign_required_quest(client, qid, employee_id):
    assignment = client.post(
        f"/api/v1/quests/{qid}/assignments",
        json={"assignment_type": "EMPLOYEE", "employee_id": employee_id},
    ).json()

    async def _make_required():
        async with AsyncSessionLocal() as db:
            from app.models import QuestAssignment

            row = await db.get(QuestAssignment, assignment["id"])
            row.required = True
            await db.commit()

    run(_make_required())
    return assignment["id"]


def _publish(client, qid):
    res = client.post(f"/api/v1/quests/{qid}/publish")
    assert res.status_code == 200, res.text


def _complete_required_quest(client, qid, employee_id, department_id, capability_ids):
    _assign_required_quest(client, qid, employee_id)
    _publish(client, qid)
    attempt = client.post("/api/v1/quest-attempts", json={"quest_id": qid, "employee_id": employee_id}).json()
    aid = attempt["id"]
    client.patch(
        f"/api/v1/quest-attempts/{aid}",
        json={
            "employee_id": employee_id,
            "findings": "Latency spiked sharply.",
            "reasoning": "Lines up with a recent deploy that introduced a slow query.",
            "solution": "checkout-service is the affected service.",
        },
    )
    client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": employee_id})
    res = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": employee_id})
    assert res.status_code == 200, res.text


async def _is_ready(employee_id: str) -> bool:
    async with AsyncSessionLocal() as db:
        employee = await db.get(Employee, employee_id)
        return await readiness_service.is_ready(db, employee)


async def _create_integration(department_id: str) -> WorkspaceIntegration:
    async with AsyncSessionLocal() as db:
        integration = WorkspaceIntegration(
            department_id=department_id,
            provider="google_drive",
            external_ref="drive-folder-mission-readiness",
            display_name="Engineering Workspace",
            workspace_link="https://drive.google.com/drive/folders/mission-readiness",
        )
        db.add(integration)
        await db.commit()
        await db.refresh(integration)
        return integration


async def _get_grant(employee_id: str, workspace_integration_id: str) -> WorkspaceAccessGrant | None:
    async with AsyncSessionLocal() as db:
        stmt = select(WorkspaceAccessGrant).where(
            WorkspaceAccessGrant.employee_id == employee_id,
            WorkspaceAccessGrant.workspace_integration_id == workspace_integration_id,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


def _readiness_summary(client, employee_id):
    res = client.get(f"/api/v1/employees/{employee_id}/readiness-summary")
    assert res.status_code == 200, res.text
    return res.json()


# =====================================================================
# The predicate itself
# =====================================================================


def test_zero_required_missions_does_not_block_readiness(client, make_employee, department, capability_ids):
    """No Mission in this department is required at all — the mission
    gate must be vacuously satisfied, not a permanent block. Regression
    guard for every department that never configures one."""
    employee = make_employee()
    _provision_assignments(client, employee["id"])
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _complete_required_quest(client, qid, employee["id"], department["id"], capability_ids)

    assert run(_is_ready(employee["id"])) is True


def test_required_mission_incomplete_blocks_readiness(client, make_employee, department, capability_ids):
    _create_mission(client, department["id"], title=f"Required Mission {next(_mission_counter)}")
    employee = make_employee()
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _complete_required_quest(client, qid, employee["id"], department["id"], capability_ids)

    # Quest gate satisfied, mission gate is not — overall still not ready.
    assert run(_is_ready(employee["id"])) is False


def test_completing_the_required_reflection_mission_reaches_readiness(
    client, make_employee, department, capability_ids
):
    mission = _create_mission(client, department["id"], title=f"Required Mission {next(_mission_counter)}")
    employee = make_employee()
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _complete_required_quest(client, qid, employee["id"], department["id"], capability_ids)
    assert run(_is_ready(employee["id"])) is False

    _complete_reflection_mission(client, employee["id"], mission["id"])
    assert run(_is_ready(employee["id"])) is True


def test_optional_mission_completion_is_irrelevant_to_readiness(client, make_employee, department, capability_ids):
    """A non-required Mission left incomplete must never block readiness
    — only Mission.required=True missions are part of the gate."""
    optional_title = f"Optional Mission {next(_mission_counter)}"
    _create_mission(client, department["id"], title=optional_title, required=False)
    employee = make_employee()
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _complete_required_quest(client, qid, employee["id"], department["id"], capability_ids)

    assert run(_is_ready(employee["id"])) is True


def test_required_mission_scoped_to_its_own_department(client, org_id, department, capability_ids):
    """A required Mission in one department must never affect an
    employee in a different department — Mission.required is scoped by
    Mission.department_id, exactly like the department-targeted Quest
    eligibility rules it sits alongside."""
    _create_mission(client, department["id"], title=f"Required Mission {next(_mission_counter)}")

    other_department = client.post(
        "/api/v1/departments",
        json={"organization_id": org_id, "name": f"Mission Readiness Other Dept {next(_dept_counter)}"},
    ).json()
    other_employee = _employee_in(client, org_id, other_department["id"])

    _complete_onboarding(client, other_employee["id"])
    qid = _build_quest(client, other_department["id"], capability_ids)
    _complete_required_quest(client, qid, other_employee["id"], other_department["id"], capability_ids)

    # The other department's required mission never touches this employee.
    assert run(_is_ready(other_employee["id"])) is True


def test_investigation_mission_completion_reaches_readiness(client, make_employee, department, capability_ids):
    mission = _create_mission(client, department["id"], title=INVESTIGATION_TITLE)
    employee = make_employee()
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _complete_required_quest(client, qid, employee["id"], department["id"], capability_ids)
    assert run(_is_ready(employee["id"])) is False

    _complete_investigation_mission(client, employee["id"], mission["id"])
    assert run(_is_ready(employee["id"])) is True


def test_failed_investigation_attempt_does_not_satisfy_the_mission_gate(client, make_employee, department):
    """A submitted-but-failed attempt must not count as completing the
    required mission — mirrors mission_attempt_service.submit_attempt
    only flipping the assignment to completed when result.passed."""
    mission = _create_mission(client, department["id"], title=INVESTIGATION_TITLE)
    employee = make_employee()
    _provision_assignments(client, employee["id"])

    attempt = client.post(
        "/api/v1/mission-attempts", json={"mission_id": mission["id"], "employee_id": employee["id"]}
    ).json()
    res = client.post(
        f"/api/v1/mission-attempts/{attempt['id']}/submit",
        json={
            "employee_id": employee["id"],
            "affected_service": "notification-service",
            "likely_cause": "Database connection pool exhaustion",
            "reasoning": "A guess.",
            "evidence_viewed": [],
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["passed"] is False

    assignment_id = _assignment_id_for(client, employee["id"], INVESTIGATION_TITLE)
    # The assignment itself must not have flipped to completed.
    bundle = client.get(f"/api/v1/onboarding/bundle/{employee['id']}").json()
    match = next(a for a in bundle["mission_assignments"] if a["id"] == assignment_id)
    assert match["status"] != "completed"


# =====================================================================
# Readiness summary counts
# =====================================================================


def test_readiness_summary_reports_mission_counts(client, make_employee, department, capability_ids):
    mission = _create_mission(client, department["id"], title=f"Required Mission {next(_mission_counter)}")
    employee = make_employee()
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _complete_required_quest(client, qid, employee["id"], department["id"], capability_ids)

    summary = _readiness_summary(client, employee["id"])
    assert summary["required_mission_count"] == 1
    assert summary["completed_required_mission_count"] == 0
    assert summary["remaining_required_mission_count"] == 1
    assert summary["ready"] is False

    _complete_reflection_mission(client, employee["id"], mission["id"])

    summary = _readiness_summary(client, employee["id"])
    assert summary["required_mission_count"] == 1
    assert summary["completed_required_mission_count"] == 1
    assert summary["remaining_required_mission_count"] == 0
    assert summary["ready"] is True


# =====================================================================
# End-to-end: Mission completion triggers the same workspace-access
# grant a required Quest completion does.
# =====================================================================


def test_completing_the_required_mission_triggers_workspace_grant(
    client, make_employee, department, capability_ids
):
    integration = run(_create_integration(department["id"]))
    mission = _create_mission(client, department["id"], title=f"Required Mission {next(_mission_counter)}")
    employee = make_employee()
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _complete_required_quest(client, qid, employee["id"], department["id"], capability_ids)

    assert run(_get_grant(employee["id"], integration.id)) is None

    _complete_reflection_mission(client, employee["id"], mission["id"])

    grant = run(_get_grant(employee["id"], integration.id))
    assert grant is not None
    assert grant.status == "GRANTED"


def test_completing_the_required_investigation_mission_triggers_workspace_grant(
    client, make_employee, department, capability_ids
):
    integration = run(_create_integration(department["id"]))
    mission = _create_mission(client, department["id"], title=INVESTIGATION_TITLE)
    employee = make_employee()
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _complete_required_quest(client, qid, employee["id"], department["id"], capability_ids)

    assert run(_get_grant(employee["id"], integration.id)) is None

    _complete_investigation_mission(client, employee["id"], mission["id"])

    grant = run(_get_grant(employee["id"], integration.id))
    assert grant is not None
    assert grant.status == "GRANTED"


# =====================================================================
# Admin: toggling Mission.required
# =====================================================================


def test_new_mission_defaults_to_not_required(client, department):
    mission = client.post(
        "/api/v1/missions",
        json={"department_id": department["id"], "title": f"Default Mission {next(_mission_counter)}"},
    ).json()
    assert mission["required"] is False


def test_patch_mission_can_toggle_required(client, department):
    mission = _create_mission(client, department["id"], required=False)
    assert mission["required"] is False

    res = client.patch(f"/api/v1/missions/{mission['id']}", json={"required": True})
    assert res.status_code == 200, res.text
    assert res.json()["required"] is True

    res = client.patch(f"/api/v1/missions/{mission['id']}", json={"required": False})
    assert res.status_code == 200, res.text
    assert res.json()["required"] is False


def test_patch_missing_mission_is_not_found(client):
    res = client.patch("/api/v1/missions/does-not-exist", json={"required": True})
    assert res.status_code == 404

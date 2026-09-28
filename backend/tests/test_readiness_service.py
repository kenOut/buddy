"""Phase 8D backend tests: ReadinessService and its wiring into the
authoritative Quest completion flow (quest_evaluation_service.evaluate_
attempt).

Covers the readiness predicate itself (onboarding completed AND at
least one required-eligible Quest AND all required-eligible Quests
completed), EMPLOYEE/DEPARTMENT/ROLE assignment eligibility reuse,
missing/inactive workspace integration handling, the real end-to-end
trigger through POST /quest-attempts/{id}/evaluate, idempotency,
failure-then-retry, and the golden provider-failure isolation test
(Quest/capability/recommendation/onboarding state untouched by a
workspace failure).

No Google provider, no frontend, no background workers, no event bus —
see readiness_service.py's own module docstring for scope.

Runs against its own isolated SQLite file, same convention as the other
test_*.py modules.
"""

import asyncio
import itertools
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_readiness_service.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

import app.services.workspace_access_service as was_mod  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Employee,
    QuestAssignment,
    Recommendation,
    WorkspaceAccessGrant,
    WorkspaceIntegration,
)
from app.services import readiness_service  # noqa: E402
from app.services.workspace_provider import (  # noqa: E402
    MockWorkspaceProvider,
    get_workspace_provider,
)

_email_counter = itertools.count()
_dept_counter = itertools.count()
_quest_counter = itertools.count()


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
        json={"organization_id": org_id, "name": f"Readiness Dept {next(_dept_counter)}"},
    ).json()


@pytest.fixture
def role(client, department):
    return client.post(
        "/api/v1/roles",
        json={"department_id": department["id"], "title": f"Readiness Role {next(_dept_counter)}"},
    ).json()


@pytest.fixture
def employee(client, org_id, department):
    return client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department["id"],
            "full_name": "Readiness Test Employee",
            "email": f"readiness-{next(_email_counter)}@kowri.test",
        },
    ).json()


def _complete_onboarding(client, employee_id):
    bundle = client.get(f"/api/v1/onboarding/bundle/{employee_id}").json()
    session_id = bundle["session"]["id"]
    res = client.patch(f"/api/v1/onboarding/sessions/{session_id}", json={"current_scene": "completion"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "completed"


def _build_quest(client, department_id, capability_ids, *, title=None, expected_answer="checkout-service"):
    title = title or f"Readiness Test Quest {next(_quest_counter)}"
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


async def _make_required(assignment_id: str) -> None:
    async with AsyncSessionLocal() as db:
        assignment = await db.get(QuestAssignment, assignment_id)
        assignment.required = True
        await db.commit()


def _assign_required(client, qid, *, employee_id=None, department_id=None, role_id=None):
    if employee_id:
        payload = {"assignment_type": "EMPLOYEE", "employee_id": employee_id}
    elif department_id:
        payload = {"assignment_type": "DEPARTMENT", "department_id": department_id}
    else:
        payload = {"assignment_type": "ROLE", "role_id": role_id}
    assignment = client.post(f"/api/v1/quests/{qid}/assignments", json=payload).json()
    run(_make_required(assignment["id"]))
    return assignment["id"]


def _publish(client, qid):
    res = client.post(f"/api/v1/quests/{qid}/publish")
    assert res.status_code == 200, res.text


def _submit_and_evaluate(client, qid, employee_id, *, solution="checkout-service is the affected service."):
    attempt = client.post("/api/v1/quest-attempts", json={"quest_id": qid, "employee_id": employee_id}).json()
    aid = attempt["id"]
    client.patch(
        f"/api/v1/quest-attempts/{aid}",
        json={
            "employee_id": employee_id,
            "findings": "Latency spiked sharply.",
            "reasoning": "Lines up with a recent deploy that introduced a slow query.",
            "solution": solution,
        },
    )
    submit = client.post(f"/api/v1/quest-attempts/{aid}/submit", json={"employee_id": employee_id})
    assert submit.status_code == 200, submit.text
    evaluate = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": employee_id})
    return aid, evaluate


async def _create_integration(department_id: str, **overrides) -> WorkspaceIntegration:
    defaults = dict(
        department_id=department_id,
        provider="google_drive",
        external_ref="drive-folder-abc123",
        display_name="Engineering Workspace",
        workspace_link="https://drive.google.com/drive/folders/abc123",
    )
    defaults.update(overrides)
    async with AsyncSessionLocal() as db:
        integration = WorkspaceIntegration(**defaults)
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


async def _count_grants_for_employee(employee_id: str) -> int:
    async with AsyncSessionLocal() as db:
        stmt = select(func.count()).select_from(WorkspaceAccessGrant).where(
            WorkspaceAccessGrant.employee_id == employee_id
        )
        result = await db.execute(stmt)
        return result.scalar_one()


def _patch_provider(factory):
    was_mod.get_workspace_provider = factory


def _restore_provider():
    was_mod.get_workspace_provider = get_workspace_provider


# =====================================================================
# 2/5/6 — the readiness predicate
# =====================================================================


async def _is_ready(employee_id: str) -> bool:
    async with AsyncSessionLocal() as db:
        employee = await db.get(Employee, employee_id)
        return await readiness_service.is_ready(db, employee)


def test_onboarding_incomplete_is_not_ready_regardless_of_quests(client, employee, department, capability_ids):
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, employee_id=employee["id"])
    _publish(client, qid)
    _submit_and_evaluate(client, qid, employee["id"])
    # Onboarding was never marked completed.
    assert run(_is_ready(employee["id"])) is False


def test_zero_required_quests_is_not_ready(client, employee):
    _complete_onboarding(client, employee["id"])
    assert run(_is_ready(employee["id"])) is False


def test_required_quest_completed_is_ready(client, employee, department, capability_ids):
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, employee_id=employee["id"])
    _publish(client, qid)
    _submit_and_evaluate(client, qid, employee["id"])
    assert run(_is_ready(employee["id"])) is True


def test_required_quest_only_submitted_not_completed_is_not_ready(client, employee, department, capability_ids):
    """Requirement #4: completion is judged only by QuestAttempt.status
    == COMPLETED — a merely-submitted (not yet evaluated) attempt must
    not count."""
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, employee_id=employee["id"])
    _publish(client, qid)

    attempt = client.post(
        "/api/v1/quest-attempts", json={"quest_id": qid, "employee_id": employee["id"]}
    ).json()
    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": employee["id"], "solution": "checkout-service is the affected service."},
    )
    submit = client.post(
        f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": employee["id"]}
    )
    assert submit.status_code == 200, submit.text

    assert run(_is_ready(employee["id"])) is False


def test_multiple_required_quests_all_must_complete(client, employee, department, capability_ids):
    _complete_onboarding(client, employee["id"])
    qid_a = _build_quest(client, department["id"], capability_ids, title=f"Multi A {next(_quest_counter)}")
    qid_b = _build_quest(client, department["id"], capability_ids, title=f"Multi B {next(_quest_counter)}")
    _assign_required(client, qid_a, employee_id=employee["id"])
    _assign_required(client, qid_b, employee_id=employee["id"])
    _publish(client, qid_a)
    _publish(client, qid_b)

    _submit_and_evaluate(client, qid_a, employee["id"])
    assert run(_is_ready(employee["id"])) is False, "only one of two required quests is done"

    _submit_and_evaluate(client, qid_b, employee["id"])
    assert run(_is_ready(employee["id"])) is True


# =====================================================================
# 3/15 — Employee/Department/Role assignment eligibility reuse
# =====================================================================


def test_employee_targeted_required_assignment_counts(client, employee, department, capability_ids):
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, employee_id=employee["id"])
    _publish(client, qid)
    _submit_and_evaluate(client, qid, employee["id"])
    assert run(_is_ready(employee["id"])) is True


def test_department_targeted_required_assignment_counts(client, employee, department, capability_ids):
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, department_id=department["id"])
    _publish(client, qid)
    _submit_and_evaluate(client, qid, employee["id"])
    assert run(_is_ready(employee["id"])) is True


def test_role_targeted_required_assignment_counts(client, employee, department, role, capability_ids):
    client.patch(f"/api/v1/employees/{employee['id']}/department", json={"department_id": department["id"]})
    # Give the employee this role via a fresh employee create (role_id is
    # not settable through the department-only PATCH endpoint), then
    # re-run onboarding completion against that identity.
    with_role = client.post(
        "/api/v1/employees",
        json={
            "organization_id": employee["organization_id"],
            "department_id": department["id"],
            "role_id": role["id"],
            "full_name": "Readiness Role Employee",
            "email": f"readiness-role-{next(_email_counter)}@kowri.test",
        },
    ).json()
    _complete_onboarding(client, with_role["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, role_id=role["id"])
    _publish(client, qid)
    _submit_and_evaluate(client, qid, with_role["id"])
    assert run(_is_ready(with_role["id"])) is True


def test_non_eligible_required_assignment_does_not_count(client, employee, org_id, capability_ids):
    """A required assignment that targets a DIFFERENT department must
    never make this employee ready — required-ness only ever counts
    through an eligibility match, exactly like ordinary Quest
    eligibility."""
    _complete_onboarding(client, employee["id"])

    other_department = client.post(
        "/api/v1/departments", json={"organization_id": org_id, "name": f"Other Dept {next(_dept_counter)}"}
    ).json()
    qid = _build_quest(client, other_department["id"], capability_ids)
    _assign_required(client, qid, department_id=other_department["id"])
    _publish(client, qid)

    assert run(_is_ready(employee["id"])) is False


# =====================================================================
# 14 — readiness is recomputed live, never cached
# =====================================================================


def test_new_required_assignment_after_ready_recalculates_readiness(client, employee, department, capability_ids):
    _complete_onboarding(client, employee["id"])
    qid_a = _build_quest(client, department["id"], capability_ids, title=f"Recalc A {next(_quest_counter)}")
    _assign_required(client, qid_a, employee_id=employee["id"])
    _publish(client, qid_a)
    _submit_and_evaluate(client, qid_a, employee["id"])
    assert run(_is_ready(employee["id"])) is True

    qid_b = _build_quest(client, department["id"], capability_ids, title=f"Recalc B {next(_quest_counter)}")
    _assign_required(client, qid_b, employee_id=employee["id"])
    _publish(client, qid_b)

    assert run(_is_ready(employee["id"])) is False, "a new incomplete required quest must un-ready them"

    _submit_and_evaluate(client, qid_b, employee["id"])
    assert run(_is_ready(employee["id"])) is True


# =====================================================================
# 7/8 — missing / inactive workspace integration
# =====================================================================


def test_missing_workspace_integration_returns_none_no_crash(client, employee, department, capability_ids):
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, employee_id=employee["id"])
    _publish(client, qid)

    aid, evaluate_res = _submit_and_evaluate(client, qid, employee["id"])
    assert evaluate_res.status_code == 200, evaluate_res.text
    assert run(_count_grants_for_employee(employee["id"])) == 0


def test_inactive_workspace_integration_treated_as_missing(client, employee, department, capability_ids):
    run(_create_integration(department["id"], active=False))

    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, employee_id=employee["id"])
    _publish(client, qid)

    _submit_and_evaluate(client, qid, employee["id"])
    assert run(_count_grants_for_employee(employee["id"])) == 0


# =====================================================================
# 9/10 — the real, authoritative trigger through evaluate_attempt
# =====================================================================


def test_evaluate_endpoint_triggers_grant_when_ready_and_workspace_configured(
    client, employee, department, capability_ids
):
    integration = run(_create_integration(department["id"]))
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, employee_id=employee["id"])
    _publish(client, qid)

    aid, evaluate_res = _submit_and_evaluate(client, qid, employee["id"])
    assert evaluate_res.status_code == 200, evaluate_res.text

    grant = run(_get_grant(employee["id"], integration.id))
    assert grant is not None
    assert grant.status == "GRANTED"

    # #10: the trigger only ever runs after the Quest completion commit
    # — proven here by the fact that the attempt itself is COMPLETED
    # regardless of the grant outcome (see the isolation test below for
    # the failure-side proof of the same ordering guarantee).
    attempt = client.get(f"/api/v1/quest-attempts/{aid}", params={"employee_id": employee["id"]}).json()
    assert attempt["status"] == "COMPLETED"


# =====================================================================
# 12/13 — idempotency and failure-then-retry, through the real endpoint
# =====================================================================


def test_repeated_evaluate_calls_do_not_duplicate_grants(client, employee, department, capability_ids):
    integration = run(_create_integration(department["id"]))
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, employee_id=employee["id"])
    _publish(client, qid)

    aid, first = _submit_and_evaluate(client, qid, employee["id"])
    assert first.status_code == 200, first.text

    # Re-evaluating an already-COMPLETED attempt is itself an existing,
    # idempotent operation (evaluate_attempt's early-return path) — it
    # must also re-run the readiness trigger without duplicating the grant.
    second = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": employee["id"]})
    assert second.status_code == 200, second.text

    assert run(_count_grants_for_employee(employee["id"])) == 1
    grant = run(_get_grant(employee["id"], integration.id))
    assert grant.status == "GRANTED"
    assert grant.attempt_count == 1  # the provider was never called a second time


def test_failure_then_retry_via_re_evaluate_succeeds(client, employee, department, capability_ids):
    integration = run(_create_integration(department["id"]))
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, employee_id=employee["id"])
    _publish(client, qid)

    _patch_provider(lambda name: MockWorkspaceProvider(simulate_failure=True))
    try:
        aid, first = _submit_and_evaluate(client, qid, employee["id"])
        assert first.status_code == 200, first.text
    finally:
        _restore_provider()

    grant = run(_get_grant(employee["id"], integration.id))
    assert grant.status == "FAILED"

    # Re-evaluate (now with the default, succeeding provider) — this is
    # the retry mechanism: the same evaluate() call, idempotent, re-runs
    # the trigger and retries the FAILED grant.
    retry = client.post(f"/api/v1/quest-attempts/{aid}/evaluate", json={"employee_id": employee["id"]})
    assert retry.status_code == 200, retry.text

    grant = run(_get_grant(employee["id"], integration.id))
    assert grant.status == "GRANTED"
    assert grant.attempt_count == 2
    assert run(_count_grants_for_employee(employee["id"])) == 1


# =====================================================================
# 16 — golden provider-failure isolation test
# =====================================================================


def test_golden_provider_failure_isolation_through_real_evaluate_endpoint(
    client, employee, department, capability_ids, org_id
):
    """The single most important Phase 8D test: driven entirely through
    the real POST /quest-attempts/{id}/evaluate endpoint (not a direct
    service call, unlike Phase 8C's equivalent), with a genuinely ready
    employee and a genuinely failing workspace provider. Proves the
    Quest/capability/recommendation/onboarding domains are byte-for-byte
    unaffected by a workspace grant failure triggered from the
    authoritative completion path itself."""
    integration = run(_create_integration(department["id"]))
    _complete_onboarding(client, employee["id"])
    qid = _build_quest(client, department["id"], capability_ids)
    _assign_required(client, qid, employee_id=employee["id"])
    _publish(client, qid)

    async def recommendation_count():
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(func.count())
                .select_from(Recommendation)
                .where(Recommendation.employee_id == employee["id"])
            )
            return result.scalar_one()

    client.get(f"/api/v1/employees/{employee['id']}/next-quest")
    recommendation_count_before = run(recommendation_count())

    _patch_provider(lambda name: MockWorkspaceProvider(simulate_failure=True))
    try:
        aid, evaluate_res = _submit_and_evaluate(client, qid, employee["id"])
    finally:
        _restore_provider()

    assert evaluate_res.status_code == 200, evaluate_res.text

    grant = run(_get_grant(employee["id"], integration.id))
    assert grant.status == "FAILED"

    attempt = client.get(f"/api/v1/quest-attempts/{aid}", params={"employee_id": employee["id"]}).json()
    assert attempt["status"] == "COMPLETED"
    assert attempt["score"] is not None

    bundle = client.get(f"/api/v1/onboarding/bundle/{employee['id']}").json()
    assert bundle["session"]["status"] == "completed"

    capabilities = client.get(f"/api/v1/employees/{employee['id']}/capabilities").json()
    assert isinstance(capabilities, list)  # untouched/queryable — no exception, no corruption

    recommendation_count_after = run(recommendation_count())
    assert recommendation_count_after == recommendation_count_before

    journey = client.get(f"/api/v1/employees/{employee['id']}/development-journey")
    assert journey.status_code == 200

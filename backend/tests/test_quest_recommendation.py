"""Phase 6C backend tests: Capability Gap Analysis + deterministic Quest
Recommendation — the adaptive loop:

    Quest -> QuestAttempt -> Evaluation -> CapabilityEvidence
    -> CapabilityProfile -> Gap Analysis -> Next Quest Recommendation

Runs against an isolated SQLite file, deleted and recreated each run —
same convention as the other test_quest_*.py modules.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent.parent / "test_quest_recommendation.db"
TEST_DB_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import asyncio  # noqa: E402

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
    """A dedicated department, created fresh for this module — NOT the
    shared demo department. Test files in this suite all end up sharing
    one physical SQLite database when run together in a single pytest
    process (app.db.session builds its engine once, at first import, from
    whatever DATABASE_URL was set at that moment — a pre-existing fact of
    this test infrastructure, not something Phase 6C changes). Other
    files' DEPARTMENT-wide QuestAssignments against the shared demo
    department would otherwise leak eligibility into every employee
    created here, breaking this file's "no other quest exists" and exact
    ranking assertions. A brand-new department has zero assignments
    against it except the ones this file creates itself."""
    res = client.post(
        "/api/v1/departments", json={"organization_id": org_id, "name": "6C Recommendation Tests Dept"}
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


@pytest.fixture(scope="module")
def capability_ids(client):
    caps = client.get("/api/v1/capabilities").json()
    return {c["key"]: c["id"] for c in caps}


_employee_counter = 0


def _new_employee(client, org_id, department_id, *, name_prefix="6C Employee"):
    global _employee_counter
    _employee_counter += 1
    res = client.post(
        "/api/v1/employees",
        json={
            "organization_id": org_id,
            "department_id": department_id,
            "full_name": f"{name_prefix} {_employee_counter}",
            "email": f"6c-employee-{_employee_counter}@buddy.dev",
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


def _make_simple_published_quest(client, quest_type, capability_id, employee_id, *, title):
    """A minimal, always-valid quest of the given type, mapped to exactly
    one capability, assigned to one employee, and published."""
    task_type_by_quest_type = {
        "OTHER": "OTHER",
        "TROUBLESHOOT": "INVESTIGATE",
        "INVESTIGATE": "INVESTIGATE",
        "DESIGN": "DESIGN",
        "BUILD": "BUILD",
    }
    quest = _new_quest(client, quest_type, "GENERAL", title=title)
    _add_task(client, quest["id"], task_type_by_quest_type.get(quest_type, "OTHER"))
    if quest_type in ("TROUBLESHOOT", "INVESTIGATE"):
        _add_evidence(client, quest["id"])
    _add_criterion(client, quest["id"], criterion_type="QUALITATIVE", description="Was this done well?")
    _map_capability(client, quest["id"], capability_id)
    _assign_employee(client, quest["id"], employee_id)
    return _publish(client, quest["id"])


def _set_capability_level(employee_id: str, capability_key: str, level: str) -> None:
    """Direct profile injection — bypasses the evidence pipeline entirely
    to set up precise, controlled capability-level scenarios for the
    recommendation-ranking tests below. The one true end-to-end test
    (test_full_loop_...) deliberately does NOT use this — it goes
    through the real evaluate_attempt -> CapabilityEvidence ->
    capability_aggregation pipeline, to prove the whole loop actually
    works, not just that this shortcut is consistent with it."""
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


# =====================================================================
# 1-2: DEVELOPING is prioritized, STRONG is not
# =====================================================================


def test_developing_capability_quest_is_recommended(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")

    quest = _make_simple_published_quest(
        client, "OTHER", capability_ids["documentation"], employee_id, title="Documentation practice"
    )

    result = _next_quest(client, employee_id)
    assert result["recommended_quest"] is not None
    assert result["recommended_quest"]["id"] == quest["id"]
    assert "documentation" in result["target_capabilities"]
    assert "developing" in result["reason"].lower()


def test_strong_capability_quest_not_unnecessarily_prioritized(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "troubleshooting", "STRONG")
    _set_capability_level(employee_id, "documentation", "DEVELOPING")

    quest_strong = _make_simple_published_quest(
        client, "OTHER", capability_ids["troubleshooting"], employee_id, title="Strong-only quest"
    )
    quest_developing = _make_simple_published_quest(
        client, "OTHER", capability_ids["documentation"], employee_id, title="Developing-target quest"
    )

    result = _next_quest(client, employee_id)
    assert result["recommended_quest"]["id"] == quest_developing["id"]
    assert result["recommended_quest"]["id"] != quest_strong["id"]


# =====================================================================
# 3-4: NOT_OBSERVED is distinct from DEVELOPING
# =====================================================================


def test_not_observed_distinct_from_developing(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")
    # independence untouched -> NOT_OBSERVED by default

    result = _next_quest(client, employee_id)
    gap = result["gap_analysis"]
    dev_keys = {i["capability"] for i in gap["development_areas"]}
    unobserved_keys = {i["capability"] for i in gap["unobserved"]}

    assert "documentation" in dev_keys
    assert "documentation" not in unobserved_keys
    assert "independence" in unobserved_keys
    assert "independence" not in dev_keys
    # every assessed item carries an honest category, never blended
    assert unobserved_keys.isdisjoint(dev_keys)


def test_unobserved_capability_can_produce_a_recommendation(client, org_id, department_id, capability_ids):
    """A brand new employee with zero evidence — every capability is
    NOT_OBSERVED. The one eligible quest still gets recommended; an
    unobserved capability is useful evidence, not something to withhold
    a recommendation over."""
    employee_id = _new_employee(client, org_id, department_id)

    quest = _make_simple_published_quest(
        client, "OTHER", capability_ids["independence"], employee_id, title="Independence opportunity"
    )

    result = _next_quest(client, employee_id)
    assert result["recommended_quest"]["id"] == quest["id"]
    assert "independence" in result["target_capabilities"]
    assert "observed" in result["reason"].lower()


# =====================================================================
# 5-9: eligibility / lifecycle rules remain authoritative
# =====================================================================


def test_completed_quest_not_recommended_again(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")

    quest = _make_simple_published_quest(
        client, "OTHER", capability_ids["documentation"], employee_id, title="Will be completed"
    )
    assert _next_quest(client, employee_id)["recommended_quest"]["id"] == quest["id"]

    attempt = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest["id"], "employee_id": employee_id}
    ).json()
    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": employee_id, "solution": "Documented the process thoroughly."},
    )
    submit = client.post(
        f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": employee_id}
    )
    assert submit.status_code == 200, submit.text
    evaluate = client.post(
        f"/api/v1/quest-attempts/{attempt['id']}/evaluate", json={"employee_id": employee_id}
    )
    assert evaluate.status_code == 200, evaluate.text

    result = _next_quest(client, employee_id)
    if result["recommended_quest"] is not None:
        assert result["recommended_quest"]["id"] != quest["id"]


def test_draft_quest_never_recommended(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")

    draft = _new_quest(client, "OTHER", "GENERAL", title="Still a draft")
    _add_task(client, draft["id"], "OTHER")
    _add_criterion(client, draft["id"], criterion_type="QUALITATIVE", description="ok")
    _map_capability(client, draft["id"], capability_ids["documentation"])
    _assign_employee(client, draft["id"], employee_id)
    # deliberately never published

    result = _next_quest(client, employee_id)
    if result["recommended_quest"] is not None:
        assert result["recommended_quest"]["id"] != draft["id"]
    else:
        assert result["reason"] == "No suitable published Quest is currently available."


def test_archived_quest_never_recommended(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")

    quest = _make_simple_published_quest(
        client, "OTHER", capability_ids["documentation"], employee_id, title="Will be archived"
    )
    client.post(f"/api/v1/quests/{quest['id']}/archive")

    result = _next_quest(client, employee_id)
    if result["recommended_quest"] is not None:
        assert result["recommended_quest"]["id"] != quest["id"]


def test_ineligible_quest_never_recommended(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    other_employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")

    # assigned to a DIFFERENT employee only
    quest = _make_simple_published_quest(
        client, "OTHER", capability_ids["documentation"], other_employee_id, title="Not for this employee"
    )

    result = _next_quest(client, employee_id)
    if result["recommended_quest"] is not None:
        assert result["recommended_quest"]["id"] != quest["id"]


def test_assignment_eligibility_remains_authoritative(client, org_id, department_id, capability_ids):
    # A second, distinct department from the module's `department_id`
    # fixture — a DEPARTMENT assignment makes every employee in that
    # department eligible, and every other test in this module creates
    # employees via `department_id`. Reusing it here would leak
    # eligibility for this quest into every employee created afterward.
    dept_res = client.post(
        "/api/v1/departments", json={"organization_id": org_id, "name": "6C Isolated Dept"}
    )
    assert dept_res.status_code == 201, dept_res.text
    isolated_dept_id = dept_res.json()["id"]

    employee_id = _new_employee(client, org_id, isolated_dept_id)
    _set_capability_level(employee_id, "communication", "DEVELOPING")

    quest = _new_quest(client, "OTHER", "GENERAL", title="Department-assigned quest")
    _add_task(client, quest["id"], "OTHER")
    _add_criterion(client, quest["id"], criterion_type="QUALITATIVE", description="ok")
    _map_capability(client, quest["id"], capability_ids["communication"])
    client.post(
        f"/api/v1/quests/{quest['id']}/assignments",
        json={"assignment_type": "DEPARTMENT", "department_id": isolated_dept_id},
    )
    _publish(client, quest["id"])

    result = _next_quest(client, employee_id)
    assert result["recommended_quest"]["id"] == quest["id"]

    # An employee in a different department must NOT be eligible.
    outsider_id = _new_employee(client, org_id, department_id, name_prefix="Outsider")
    outsider_result = _next_quest(client, outsider_id)
    if outsider_result["recommended_quest"] is not None:
        assert outsider_result["recommended_quest"]["id"] != quest["id"]


# =====================================================================
# 10-12: target capability accuracy, explanation, empty state
# =====================================================================


def test_multi_capability_quest_produces_correct_target_set(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")
    _set_capability_level(employee_id, "communication", "DEVELOPING")
    _set_capability_level(employee_id, "problem_solving", "CAPABLE")

    quest = _new_quest(client, "OTHER", "GENERAL", title="Multi-capability quest")
    _add_task(client, quest["id"], "OTHER")
    _add_criterion(client, quest["id"], criterion_type="QUALITATIVE", description="ok")
    for key in ("documentation", "communication", "problem_solving"):
        _map_capability(client, quest["id"], capability_ids[key])
    _assign_employee(client, quest["id"], employee_id)
    _publish(client, quest["id"])

    result = _next_quest(client, employee_id)
    assert result["recommended_quest"]["id"] == quest["id"]
    # Target set = the DEVELOPING ones that drove the tier — not the
    # CAPABLE one also mapped to the same quest.
    assert set(result["target_capabilities"]) == {"documentation", "communication"}


def test_recommendation_explanation_reflects_deterministic_rules(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "independence", "NOT_OBSERVED")

    quest = _make_simple_published_quest(
        client, "OTHER", capability_ids["independence"], employee_id, title="Unobserved explanation check"
    )

    result = _next_quest(client, employee_id)
    assert result["recommended_quest"]["id"] == quest["id"]
    assert "independence" in result["reason"].lower()
    assert "observed" in result["reason"].lower()


def test_no_suitable_quest_returns_null(client, org_id, department_id):
    employee_id = _new_employee(client, org_id, department_id)
    # No quests assigned to this employee at all.
    result = _next_quest(client, employee_id)
    assert result["recommended_quest"] is None
    assert result["reason"] == "No suitable published Quest is currently available."
    assert result["target_capabilities"] == []


# =====================================================================
# 13-14: determinism and reactivity to state changes
# =====================================================================


def test_repeated_calls_return_same_recommendation(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")
    quest = _make_simple_published_quest(
        client, "OTHER", capability_ids["documentation"], employee_id, title="Stable recommendation"
    )

    def _stable_fields(result):
        # Everything that defines "the same recommendation" — excludes
        # gap_analysis.generated_at, which is genuinely fresh per call
        # (it's a "when was this computed" timestamp, not part of the
        # recommendation itself) and would otherwise make three
        # back-to-back, semantically-identical calls compare unequal.
        return (
            result["recommended_quest"]["id"] if result["recommended_quest"] else None,
            result["reason"],
            result["target_capabilities"],
        )

    first = _next_quest(client, employee_id)
    second = _next_quest(client, employee_id)
    third = _next_quest(client, employee_id)
    assert first["recommended_quest"]["id"] == quest["id"]
    assert _stable_fields(first) == _stable_fields(second) == _stable_fields(third)


def test_recommendation_changes_after_capability_profile_changes(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")

    quest_a = _make_simple_published_quest(
        client, "OTHER", capability_ids["documentation"], employee_id, title="Quest targeting documentation"
    )
    quest_b = _make_simple_published_quest(
        client, "OTHER", capability_ids["communication"], employee_id, title="Quest targeting communication"
    )

    before = _next_quest(client, employee_id)
    assert before["recommended_quest"]["id"] == quest_a["id"]

    # Documentation is now STRONG; communication becomes the only
    # DEVELOPING-mapped option among the two.
    _set_capability_level(employee_id, "documentation", "STRONG")
    _set_capability_level(employee_id, "communication", "DEVELOPING")

    after = _next_quest(client, employee_id)
    assert after["recommended_quest"]["id"] == quest_b["id"]


# =====================================================================
# 15: the full end-to-end loop, through the REAL evaluation pipeline
# =====================================================================


def test_full_loop_completing_quest_1_causes_quest_2_to_become_recommended(
    client, org_id, department_id, capability_ids
):
    """No profile injection here — this goes through the real
    submit -> evaluate -> CapabilityEvidence -> capability_aggregation
    pipeline, proving the whole adaptive loop actually works end to end,
    not just that the ranking logic is internally consistent."""
    employee_id = _new_employee(client, org_id, department_id, name_prefix="Full loop employee")

    quest_1 = _new_quest(client, "INVESTIGATE", "INVESTIGATION", title="Quest 1 — investigate the spike")
    _add_task(client, quest_1["id"], "INVESTIGATE")
    _add_evidence(client, quest_1["id"])
    _add_criterion(
        client, quest_1["id"], criterion_type="DETERMINISTIC", expected_answer="checkout-service"
    )
    _map_capability(client, quest_1["id"], capability_ids["troubleshooting"])
    _assign_employee(client, quest_1["id"], employee_id)
    _publish(client, quest_1["id"])

    quest_2 = _new_quest(client, "OTHER", "GENERAL", title="Quest 2 — documentation follow-up")
    _add_task(client, quest_2["id"], "OTHER")
    _add_criterion(client, quest_2["id"], criterion_type="QUALITATIVE", description="ok")
    _map_capability(client, quest_2["id"], capability_ids["documentation"])
    _assign_employee(client, quest_2["id"], employee_id)
    _publish(client, quest_2["id"])

    # Before any work: both employee capabilities are NOT_OBSERVED, so
    # both quests sit at the same tier — whichever wins the deterministic
    # tiebreak is quest_1 or quest_2, either is a valid starting point.
    before = _next_quest(client, employee_id)
    assert before["recommended_quest"] is not None

    # Complete Quest 1 for real.
    attempt = client.post(
        "/api/v1/quest-attempts", json={"quest_id": quest_1["id"], "employee_id": employee_id}
    ).json()
    client.patch(
        f"/api/v1/quest-attempts/{attempt['id']}",
        json={"employee_id": employee_id, "solution": "checkout-service is the affected service."},
    )
    submit = client.post(
        f"/api/v1/quest-attempts/{attempt['id']}/submit", json={"employee_id": employee_id}
    )
    assert submit.status_code == 200, submit.text
    evaluate = client.post(
        f"/api/v1/quest-attempts/{attempt['id']}/evaluate", json={"employee_id": employee_id}
    )
    assert evaluate.status_code == 200, evaluate.text

    # Verify the real pipeline actually produced evidence + a profile.
    evidence = client.get(f"/api/v1/employees/{employee_id}/capabilities/evidence").json()
    assert any(e["quest_attempt_id"] == attempt["id"] for e in evidence)
    profiles = client.get(f"/api/v1/employees/{employee_id}/capabilities").json()
    troubleshooting_profile = next(p for p in profiles if p["capability"]["key"] == "troubleshooting")
    assert troubleshooting_profile["level"] in ("DEVELOPING", "CAPABLE", "STRONG")
    assert troubleshooting_profile["evidence_count"] > 0

    # Quest 1 is completed and must never be recommended again; Quest 2
    # (documentation, still NOT_OBSERVED/untouched) must now be next.
    after = _next_quest(client, employee_id)
    assert after["recommended_quest"] is not None
    assert after["recommended_quest"]["id"] == quest_2["id"]
    assert after["recommended_quest"]["id"] != quest_1["id"]


# =====================================================================
# 16-17: recommendation is read-only
# =====================================================================


def test_recommendation_does_not_create_an_attempt(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")
    quest = _make_simple_published_quest(
        client, "OTHER", capability_ids["documentation"], employee_id, title="No attempt side effect"
    )

    _next_quest(client, employee_id)
    _next_quest(client, employee_id)

    # No attempt exists yet — GET on a nonexistent (quest, employee)
    # attempt correctly 404s via the eligibility-gated creation endpoint
    # never having been called.
    async def count_attempts():
        from sqlalchemy import func, select

        from app.db.session import AsyncSessionLocal
        from app.models import QuestAttempt

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(func.count()).select_from(QuestAttempt).where(
                    QuestAttempt.quest_id == quest["id"], QuestAttempt.employee_id == employee_id
                )
            )
            return result.scalar_one()

    assert asyncio.run(count_attempts()) == 0


def test_recommendation_does_not_mutate_assignments(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")
    quest = _make_simple_published_quest(
        client, "OTHER", capability_ids["documentation"], employee_id, title="No assignment mutation"
    )

    before = client.get(f"/api/v1/quests/{quest['id']}/assignments").json()
    _next_quest(client, employee_id)
    after = client.get(f"/api/v1/quests/{quest['id']}/assignments").json()
    assert before == after


# =====================================================================
# 18: employee-safe response never leaks hidden evaluator fields
# =====================================================================


def test_employee_safe_response_has_no_hidden_evaluator_fields(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")

    quest = _new_quest(client, "OTHER", "GENERAL", title="6C leak check quest")
    _add_task(client, quest["id"], "OTHER")
    _add_criterion(
        client,
        quest["id"],
        criterion_type="DETERMINISTIC",
        expected_answer="SECRET_6C_EXPECTED_ANSWER",
        expected_behavior="SECRET_6C_EXPECTED_BEHAVIOR",
        reference_solution="SECRET_6C_REFERENCE_SOLUTION",
    )
    _map_capability(client, quest["id"], capability_ids["documentation"])
    _assign_employee(client, quest["id"], employee_id)
    _publish(client, quest["id"])

    res = client.get(f"/api/v1/employees/{employee_id}/next-quest")
    assert res.status_code == 200
    text = res.text
    for secret in (
        "SECRET_6C_EXPECTED_ANSWER",
        "SECRET_6C_EXPECTED_BEHAVIOR",
        "SECRET_6C_REFERENCE_SOLUTION",
    ):
        assert secret not in text
    assert "expected_answer" not in text
    assert "expected_behavior" not in text
    assert "reference_solution" not in text
    assert "evaluation_criteria" not in text


# =====================================================================
# 19-20: cross-employee / cross-quest isolation
# =====================================================================


def test_cross_employee_access_is_isolated(client, org_id, department_id, capability_ids):
    employee_a = _new_employee(client, org_id, department_id, name_prefix="Cross A")
    employee_b = _new_employee(client, org_id, department_id, name_prefix="Cross B")
    _set_capability_level(employee_a, "documentation", "DEVELOPING")
    _set_capability_level(employee_b, "communication", "DEVELOPING")

    quest_a = _make_simple_published_quest(
        client, "OTHER", capability_ids["documentation"], employee_a, title="Only for A"
    )
    quest_b = _make_simple_published_quest(
        client, "OTHER", capability_ids["communication"], employee_b, title="Only for B"
    )

    result_a = _next_quest(client, employee_a)
    result_b = _next_quest(client, employee_b)
    assert result_a["recommended_quest"]["id"] == quest_a["id"]
    assert result_b["recommended_quest"]["id"] == quest_b["id"]
    assert result_a["recommended_quest"]["id"] != quest_b["id"]
    assert result_b["recommended_quest"]["id"] != quest_a["id"]


def test_cross_quest_isolation(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")
    quest = _make_simple_published_quest(
        client, "OTHER", capability_ids["documentation"], employee_id, title="Isolation target"
    )

    unrelated_quest = _new_quest(client, "OTHER", "GENERAL", title="Unrelated quest")
    _add_task(client, unrelated_quest["id"], "OTHER")

    _next_quest(client, employee_id)

    # The recommendation call must not have touched the unrelated quest's
    # own tasks/state at all.
    unrelated_tasks = client.get(f"/api/v1/quests/{unrelated_quest['id']}/tasks").json()
    assert len(unrelated_tasks) == 1


# =====================================================================
# 21: concurrency
# =====================================================================


def test_concurrent_reads_return_consistent_recommendation(client, org_id, department_id, capability_ids):
    employee_id = _new_employee(client, org_id, department_id)
    _set_capability_level(employee_id, "documentation", "DEVELOPING")
    quest = _make_simple_published_quest(
        client, "OTHER", capability_ids["documentation"], employee_id, title="Concurrent read target"
    )

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: _next_quest(client, employee_id), range(8)))

    quest_ids = {r["recommended_quest"]["id"] for r in responses}
    assert quest_ids == {quest["id"]}


# =====================================================================
# 22: existing Mission recommendation flow is unaffected
# =====================================================================


def test_existing_mission_recommendation_flow_unaffected(client):
    bundle = client.get("/api/v1/onboarding/bundle/demo").json()
    res = client.get(f"/api/v1/employees/{bundle['employee']['id']}/next-mission")
    assert res.status_code == 200
    body = res.json()
    assert "reason" in body
    assert "target_capabilities" in body

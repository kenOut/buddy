"""Manager Performance & Readiness Visibility — Stage 1.

Orchestration only — every fact returned here comes from an existing,
unmodified service (readiness_service, capability_service,
mission_service, mission_attempt_service, quest_service,
quest_assignment_service, quest_attempt_service, department_service).
Nothing in this module computes a score, evaluates an attempt,
recomputes a capability profile, or changes what "ready" means — it
reads what those modules already produced and reshapes it into the
manager-safe schemas defined in schemas/manager_performance.py.

`blockers` is the one piece of light synthesis this module does: turning
readiness_service's already-public required-vs-completed id sets
(required_eligible_quest_ids/required_eligible_mission_ids) into
plain-language strings, using the same Quest/Mission titles already
fetched for the missions[]/quests[] sections below — not a second,
independently-invented notion of "what's blocking readiness."
"""

from statistics import mean

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee
from app.schemas.manager_performance import (
    ManagerCapabilitySummary,
    ManagerEmployeeInfo,
    ManagerEmployeePerformanceResponse,
    ManagerMissionPerformance,
    ManagerPerformanceSummary,
    ManagerQuestPerformance,
    ManagerReadinessInfo,
)
from app.services import (
    capability_service,
    department_service,
    mission_attempt_service,
    mission_service,
    quest_assignment_service,
    quest_attempt_service,
    quest_service,
    readiness_service,
)


async def _build_employee_info(db: AsyncSession, employee: Employee) -> ManagerEmployeeInfo:
    department_name = None
    if employee.department_id:
        department = await department_service.get_department(db, employee.department_id)
        department_name = department.name if department else None

    return ManagerEmployeeInfo(
        id=employee.id,
        full_name=employee.full_name,
        email=employee.email,
        job_title=employee.job_title,
        department_id=employee.department_id,
        department_name=department_name,
        team=employee.team,
    )


async def _build_mission_performance(
    db: AsyncSession, employee_id: str
) -> list[ManagerMissionPerformance]:
    # Two bulk queries, not one per assignment — list_assignments_for_employee
    # already eager-loads .mission; list_attempts_for_employee (added
    # alongside this stage) mirrors the equivalent Quest-side bulk read.
    assignments = await mission_service.list_assignments_for_employee(db, employee_id)
    attempts = await mission_attempt_service.list_attempts_for_employee(db, employee_id)
    attempt_by_mission_id = {a.mission_id: a for a in attempts}

    results = []
    for assignment in assignments:
        attempt = attempt_by_mission_id.get(assignment.mission_id)
        results.append(
            ManagerMissionPerformance(
                id=assignment.mission_id,
                title=assignment.mission.title,
                required=assignment.mission.required,
                assignment_status=assignment.status,
                attempt_status=attempt.status if attempt else None,
                score=attempt.score if attempt else None,
                passed=attempt.passed if attempt else None,
                feedback=attempt.feedback if attempt else None,
                completed_at=assignment.completed_at,
            )
        )
    return results


async def _build_quest_performance(
    db: AsyncSession, employee: Employee, required_quest_ids: set[str]
) -> tuple[list[ManagerQuestPerformance], dict]:
    # Same eligibility resolution the employee's own Quest list already
    # uses (quests.py's list_employee_quests) — not a second,
    # independently-derived notion of "which quests does this employee
    # have."
    eligible_ids = await quest_assignment_service.list_eligible_quest_ids_for_employee(db, employee)
    quests = await quest_service.list_quests_by_ids(db, eligible_ids)
    attempts = await quest_attempt_service.list_attempts_for_employee(db, employee.id)
    attempt_by_quest_id = {a.quest_id: a for a in attempts}

    results = []
    for quest in quests:
        attempt = attempt_by_quest_id.get(quest.id)
        results.append(
            ManagerQuestPerformance(
                id=quest.id,
                title=quest.title,
                required=quest.id in required_quest_ids,
                attempt_status=attempt.status if attempt else None,
                score=attempt.score if attempt else None,
                passed=attempt.passed if attempt else None,
                feedback=attempt.feedback if attempt else None,
                completed_at=attempt.completed_at if attempt else None,
            )
        )
    return results, {q.id: q for q in quests}


async def _build_capabilities(db: AsyncSession, employee_id: str) -> list[ManagerCapabilitySummary]:
    profiles = await capability_service.list_profiles_for_employee(db, employee_id)
    return [
        ManagerCapabilitySummary(
            capability_id=profile.capability_id,
            capability_key=profile.capability.key,
            capability_name=profile.capability.name,
            level=profile.level,
            confidence=profile.confidence,
            evidence_count=profile.evidence_count,
        )
        for profile in profiles
    ]


def _build_blockers(
    *,
    onboarding_completed: bool,
    required_quest_ids: set[str],
    quest_by_id: dict,
    quest_attempt_status_by_id: dict[str, str],
    required_mission_ids: set[str],
    mission_title_by_id: dict[str, str],
    mission_assignment_status_by_id: dict[str, str],
) -> list[str]:
    blockers: list[str] = []
    if not onboarding_completed:
        blockers.append("Onboarding has not been completed yet.")

    for quest_id in sorted(required_quest_ids, key=lambda qid: quest_by_id[qid].title):
        if quest_attempt_status_by_id.get(quest_id) != "COMPLETED":
            blockers.append(f'Required quest "{quest_by_id[quest_id].title}" is incomplete.')

    for mission_id in sorted(required_mission_ids, key=lambda mid: mission_title_by_id.get(mid, "")):
        if mission_assignment_status_by_id.get(mission_id) != "completed":
            title = mission_title_by_id.get(mission_id, "Untitled mission")
            blockers.append(f'Required mission "{title}" is incomplete.')

    return blockers


async def get_employee_performance(
    db: AsyncSession, employee: Employee
) -> ManagerEmployeePerformanceResponse:
    employee_info = await _build_employee_info(db, employee)

    required_quest_ids = await readiness_service.required_eligible_quest_ids(db, employee)
    required_mission_ids = await readiness_service.required_eligible_mission_ids(db, employee)

    missions = await _build_mission_performance(db, employee.id)
    quests, quest_by_id = await _build_quest_performance(db, employee, required_quest_ids)
    capabilities = await _build_capabilities(db, employee.id)

    # required_eligible_mission_ids resolves straight from Mission rows
    # in the employee's department (readiness_service.py), independent
    # of whether a MissionAssignment row actually exists for this
    # employee — a required Mission that was created after this
    # employee's session (and therefore never got provisioned, see P2's
    # Provisioning Boundary) is a real, valid state, not an error. The
    # missions[] list above is assignment-derived and would silently
    # miss such a Mission's title, so blocker text is built from the
    # full department Mission set instead, not just the assigned subset.
    department_missions = (
        await mission_service.list_missions(db, employee.department_id)
        if employee.department_id
        else []
    )
    mission_title_by_id = {m.id: m.title for m in department_missions}

    summary = await readiness_service.get_readiness_summary(db, employee)

    blockers = _build_blockers(
        onboarding_completed=summary.onboarding_completed,
        required_quest_ids=required_quest_ids,
        quest_by_id=quest_by_id,
        quest_attempt_status_by_id={q.id: q.attempt_status for q in quests if q.attempt_status},
        required_mission_ids=required_mission_ids,
        mission_title_by_id=mission_title_by_id,
        mission_assignment_status_by_id={m.id: m.assignment_status for m in missions},
    )

    readiness = ManagerReadinessInfo(
        ready=summary.ready,
        onboarding_completed=summary.onboarding_completed,
        required_quest_count=summary.required_quest_count,
        completed_required_quest_count=summary.completed_required_quest_count,
        remaining_required_quest_count=summary.remaining_required_quest_count,
        required_mission_count=summary.required_mission_count,
        completed_required_mission_count=summary.completed_required_mission_count,
        remaining_required_mission_count=summary.remaining_required_mission_count,
        blockers=blockers,
    )

    scores = [m.score for m in missions if m.score is not None] + [
        q.score for q in quests if q.score is not None
    ]
    performance_summary = ManagerPerformanceSummary(
        missions_assigned=len(missions),
        missions_completed=sum(1 for m in missions if m.assignment_status == "completed"),
        quests_assigned=len(quests),
        quests_completed=sum(1 for q in quests if q.attempt_status == "COMPLETED"),
        scored_items=len(scores),
        average_score=round(mean(scores), 1) if scores else None,
    )

    return ManagerEmployeePerformanceResponse(
        employee=employee_info,
        readiness=readiness,
        missions=missions,
        quests=quests,
        capabilities=capabilities,
        performance_summary=performance_summary,
    )

"""Manager Performance & Readiness Visibility — Stage 1, extended by
Stage 2 (Performance-Aware Readiness).

Orchestration only — every fact returned here comes from an existing,
unmodified service (readiness_service, capability_service,
mission_service, mission_attempt_service, quest_service,
quest_assignment_service, quest_attempt_service, department_service).
Nothing in this module computes a score, evaluates an attempt,
recomputes a capability profile, or changes what "ready" means — it
reads what those modules already produced and reshapes it into the
manager-safe schemas defined in schemas/manager_performance.py.

Stage 2 removes Stage 1's own local `_build_blockers` entirely:
blockers, and each row's `minimum_score`/`threshold_status`, now come
straight from readiness_service.required_quest_items/
required_mission_items/get_readiness_blockers — the exact same
per-item state `is_ready()` itself evaluates — rather than a second,
independently-derived notion of "what's blocking readiness" computed
in this module (Stage 2 §8).
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
from app.services.readiness_service import RequiredItemState


def _threshold_status(item: RequiredItemState | None) -> tuple[float | None, str | None]:
    """(minimum_score, threshold_status) for a Mission/Quest row — None,
    None when the item isn't in the required-items list at all (not
    required for this employee). Otherwise mirrors
    RequiredItemState.satisfied exactly: INCOMPLETE if not completed,
    else SATISFIED or BELOW_THRESHOLD."""
    if item is None:
        return None, None
    if not item.completed:
        return item.minimum_score, "INCOMPLETE"
    return item.minimum_score, "SATISFIED" if item.satisfied else "BELOW_THRESHOLD"


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
    db: AsyncSession, employee: Employee, required_items_by_id: dict[str, RequiredItemState]
) -> list[ManagerMissionPerformance]:
    # Two bulk queries, not one per assignment — list_assignments_for_employee
    # already eager-loads .mission; list_attempts_for_employee (added
    # alongside Stage 1) mirrors the equivalent Quest-side bulk read.
    assignments = await mission_service.list_assignments_for_employee(db, employee.id)
    attempts = await mission_attempt_service.list_attempts_for_employee(db, employee.id)
    attempt_by_mission_id = {a.mission_id: a for a in attempts}

    results = []
    for assignment in assignments:
        attempt = attempt_by_mission_id.get(assignment.mission_id)
        minimum_score, threshold_status = _threshold_status(required_items_by_id.get(assignment.mission_id))
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
                minimum_score=minimum_score,
                threshold_status=threshold_status,
            )
        )
    return results


async def _build_quest_performance(
    db: AsyncSession, employee: Employee, required_items_by_id: dict[str, RequiredItemState]
) -> list[ManagerQuestPerformance]:
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
        required_item = required_items_by_id.get(quest.id)
        minimum_score, threshold_status = _threshold_status(required_item)
        results.append(
            ManagerQuestPerformance(
                id=quest.id,
                title=quest.title,
                required=required_item is not None,
                attempt_status=attempt.status if attempt else None,
                score=attempt.score if attempt else None,
                passed=attempt.passed if attempt else None,
                feedback=attempt.feedback if attempt else None,
                completed_at=attempt.completed_at if attempt else None,
                minimum_score=minimum_score,
                threshold_status=threshold_status,
            )
        )
    return results


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


async def get_employee_performance(
    db: AsyncSession, employee: Employee
) -> ManagerEmployeePerformanceResponse:
    employee_info = await _build_employee_info(db, employee)

    required_quest_items = await readiness_service.required_quest_items(db, employee)
    required_mission_items = await readiness_service.required_mission_items(db, employee)
    required_quest_by_id = {item.id: item for item in required_quest_items}
    required_mission_by_id = {item.id: item for item in required_mission_items}

    missions = await _build_mission_performance(db, employee, required_mission_by_id)
    quests = await _build_quest_performance(db, employee, required_quest_by_id)
    capabilities = await _build_capabilities(db, employee.id)

    summary = await readiness_service.get_readiness_summary(db, employee)
    blockers = await readiness_service.get_readiness_blockers(db, employee)

    readiness = ManagerReadinessInfo(
        ready=summary.ready,
        onboarding_completed=summary.onboarding_completed,
        required_quest_count=summary.required_quest_count,
        completed_required_quest_count=summary.completed_required_quest_count,
        remaining_required_quest_count=summary.remaining_required_quest_count,
        required_mission_count=summary.required_mission_count,
        completed_required_mission_count=summary.completed_required_mission_count,
        remaining_required_mission_count=summary.remaining_required_mission_count,
        required_items_below_threshold=summary.required_items_below_threshold,
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

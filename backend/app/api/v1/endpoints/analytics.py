"""Phase 6E — Manager Analytics: read-only endpoints under /admin's API
surface. No endpoint here writes anything; every one of them is a GET
that composes existing authoritative records (see analytics_service.py).

Kept structurally separate from the employee-facing endpoints
(quests.py, capabilities.py) — this file is never imported by, and
never shares a route prefix with, anything an employee-facing page
calls (Part 23)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models import Capability
from app.schemas.analytics import (
    AnalyticsOverviewResponse,
    CapabilityAnalyticsResponse,
    CapabilityAnalyticsSummary,
    CapabilityEmployeeItem,
    CapabilityEmployeesResponse,
    CapabilityLevelBreakdown,
    DevelopmentSignalItem,
    DevelopmentSignalsResponse,
    EmployeeAnalyticsResponse,
    EmployeeCapabilitySummary,
    EmployeeQuestActivityItem,
    EmployeeRecommendationSummary,
    QuestAnalyticsResponse,
    QuestAnalyticsSummary,
    QuestCapabilityEvidenceBreakdown,
    QuestDetailAnalyticsResponse,
    QuestEvidenceSource,
    RecentRecommendationItem,
)
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _capability_summary(row) -> CapabilityAnalyticsSummary:
    observed = sum(row.level_counts.values())
    return CapabilityAnalyticsSummary(
        capability_id=row.capability.id,
        capability_key=row.capability.key,
        capability_name=row.capability.name,
        total_employees=row.total_employees,
        observed_employees=observed,
        not_observed_employees=max(row.total_employees - observed, 0),
        level_breakdown=[
            CapabilityLevelBreakdown(level=level, employee_count=count)
            for level, count in sorted(row.level_counts.items())
            if count > 0
        ],
        development_area_employees=row.level_counts.get("DEVELOPING", 0),
        quests_producing_evidence=[
            QuestEvidenceSource(quest_id=qid, quest_title=title, evidence_count=count)
            for qid, title, count in row.quests_producing_evidence
        ],
    )


@router.get("/overview", response_model=AnalyticsOverviewResponse)
async def get_analytics_overview(department_id: str | None = None, db: AsyncSession = Depends(get_db)):
    result = await analytics_service.get_overview(db, department_id)
    recent_recommendations = [
        RecentRecommendationItem(
            recommendation_id=r.id,
            employee_id=r.employee_id,
            employee_name=result.recent_recommendation_employee_names.get(r.employee_id, "Unknown employee"),
            quest_id=r.quest_id,
            quest_title=result.recent_recommendation_quest_titles.get(r.quest_id, "A Quest that's no longer available"),
            reason=r.reason,
            target_capabilities=list(r.target_capabilities),
            created_at=r.created_at,
        )
        for r in result.recent_recommendations
    ]
    return AnalyticsOverviewResponse(
        department_id=result.department_id,
        published_quests=result.published_quests,
        draft_quests=result.draft_quests,
        archived_quests=result.archived_quests,
        active_assignment_records=result.active_assignment_records,
        employees_reached=result.employees_reached,
        attempts_total=result.attempts_total,
        attempts_not_started=result.attempts_not_started,
        attempts_in_progress=result.attempts_in_progress,
        attempts_submitted=result.attempts_submitted,
        attempts_evaluating=result.attempts_evaluating,
        attempts_completed=result.attempts_completed,
        employees_with_capability_evidence=result.employees_with_capability_evidence,
        capability_observations=result.capability_observations,
        recommendations_generated=result.recommendations_generated,
        employees_with_development_history=result.employees_with_development_history,
        recent_recommendations=recent_recommendations,
    )


@router.get("/quests", response_model=QuestAnalyticsResponse)
async def get_quest_analytics(department_id: str | None = None, db: AsyncSession = Depends(get_db)):
    rows = await analytics_service.get_quest_analytics(db, department_id)
    return QuestAnalyticsResponse(
        department_id=department_id,
        quests=[
            QuestAnalyticsSummary(
                quest_id=row.quest.id,
                title=row.quest.title,
                quest_type=row.quest.quest_type,
                status=row.quest.status,
                difficulty=row.quest.difficulty,
                project_id=row.quest.project_id,
                project_name=row.project_name,
                capability_count=row.capability_count,
                assigned_employees=row.assigned_employees,
                attempts_total=row.attempts_total,
                attempts_completed=row.attempts_completed,
                completion_rate=row.completion_rate,
                evidence_count=row.evidence_count,
                recommendation_count=row.recommendation_count,
                signals=row.signals,
            )
            for row in rows
        ],
    )


@router.get("/quests/{quest_id}", response_model=QuestDetailAnalyticsResponse)
async def get_quest_detail_analytics(
    quest_id: str, department_id: str | None = None, db: AsyncSession = Depends(get_db)
):
    result = await analytics_service.get_quest_detail_analytics(db, quest_id, department_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Quest not found")
    return QuestDetailAnalyticsResponse(
        quest_id=result.quest.id,
        title=result.quest.title,
        quest_type=result.quest.quest_type,
        status=result.quest.status,
        difficulty=result.quest.difficulty,
        project_id=result.quest.project_id,
        project_name=result.project_name,
        assigned_employees=result.assigned_employees,
        attempts_total=sum(result.status_counts.values()),
        attempts_not_started=result.status_counts.get("NOT_STARTED", 0),
        attempts_in_progress=result.status_counts.get("IN_PROGRESS", 0),
        attempts_submitted=result.status_counts.get("SUBMITTED", 0),
        attempts_evaluating=result.status_counts.get("EVALUATING", 0),
        attempts_completed=result.status_counts.get("COMPLETED", 0),
        completion_rate=result.completion_rate,
        evidence_count=result.evidence_count,
        capability_breakdown=[
            QuestCapabilityEvidenceBreakdown(capability_key=key, capability_name=name, evidence_count=count)
            for key, name, count in result.capability_breakdown
        ],
        evaluation_criteria_count=result.evaluation_criteria_count,
        recommendation_count=result.recommendation_count,
        signals=result.signals,
    )


@router.get("/capabilities", response_model=CapabilityAnalyticsResponse)
async def get_capability_analytics(department_id: str | None = None, db: AsyncSession = Depends(get_db)):
    rows = await analytics_service.get_capability_analytics(db, department_id)
    return CapabilityAnalyticsResponse(
        department_id=department_id, capabilities=[_capability_summary(row) for row in rows]
    )


@router.get("/development-signals", response_model=DevelopmentSignalsResponse)
async def get_development_signals(department_id: str | None = None, db: AsyncSession = Depends(get_db)):
    rows = await analytics_service.get_development_signals(db, department_id)
    development_areas = [
        DevelopmentSignalItem(
            capability_id=row.capability.id,
            capability_key=row.capability.key,
            capability_name=row.capability.name,
            employee_count=row.level_counts.get("DEVELOPING", 0),
        )
        for row in rows
    ]
    development_areas = [item for item in development_areas if item.employee_count > 0]
    development_areas.sort(key=lambda item: item.employee_count, reverse=True)
    return DevelopmentSignalsResponse(department_id=department_id, development_areas=development_areas)


@router.get("/employees/{employee_id}", response_model=EmployeeAnalyticsResponse)
async def get_employee_analytics(employee_id: str, db: AsyncSession = Depends(get_db)):
    result = await analytics_service.get_employee_analytics(db, employee_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    capabilities = [
        EmployeeCapabilitySummary(
            capability_key=item.capability_key,
            capability_name=item.capability_name,
            level=item.current_level,
            category=item.category,
            evidence_count=result.evidence_counts.get(item.capability_key, 0),
        )
        for item in result.gap_analysis.assessed_capabilities
    ]
    development_areas = [item.capability_key for item in result.gap_analysis.development_areas]

    recent_quest_activity = [
        EmployeeQuestActivityItem(
            quest_id=attempt.quest_id,
            quest_title=result.quest_titles.get(attempt.quest_id, "A Quest that's no longer available"),
            status=attempt.status,
            completed_at=attempt.completed_at,
        )
        for attempt in result.attempts
    ]

    latest_recommendation = None
    if result.latest_recommendation:
        latest_recommendation = EmployeeRecommendationSummary(
            quest_id=result.latest_recommendation.quest_id,
            quest_title=result.latest_recommendation_quest_title or "A Quest that's no longer available",
            reason=result.latest_recommendation.reason,
            target_capabilities=list(result.latest_recommendation.target_capabilities),
            created_at=result.latest_recommendation.created_at,
        )

    return EmployeeAnalyticsResponse(
        employee_id=result.employee.id,
        full_name=result.employee.full_name,
        department_id=result.employee.department_id,
        department_name=result.department_name,
        role_title=result.role_title,
        capabilities=capabilities,
        development_areas=development_areas,
        recent_quest_activity=recent_quest_activity,
        latest_recommendation=latest_recommendation,
    )


_VALID_CATEGORIES = {"STRENGTH", "CAPABLE", "DEVELOPMENT_AREA", "UNOBSERVED"}


@router.get("/capabilities/{capability_id}/employees", response_model=CapabilityEmployeesResponse)
async def get_capability_employees(
    capability_id: str,
    category: str,
    department_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Part 11's drill-down: turns an aggregate count from /capabilities
    (e.g. "6 employees have Documentation classified as a development
    area") into the actual employee list behind it."""
    if category not in _VALID_CATEGORIES:
        raise HTTPException(
            status_code=422, detail=f"category must be one of {sorted(_VALID_CATEGORIES)}"
        )
    capability = await db.get(Capability, capability_id)
    if capability is None:
        raise HTTPException(status_code=404, detail="Capability not found")

    rows = await analytics_service.get_capability_employees(db, capability_id, category, department_id)
    if rows is None:
        raise HTTPException(status_code=404, detail="Capability not found")

    return CapabilityEmployeesResponse(
        capability_id=capability.id,
        capability_key=capability.key,
        capability_name=capability.name,
        category=category,
        department_id=department_id,
        employees=[
            CapabilityEmployeeItem(
                employee_id=row.employee.id,
                full_name=row.employee.full_name,
                department_name=row.department_name,
                role_title=row.role_title,
                level=row.level,
                evidence_count=row.evidence_count,
            )
            for row in rows
        ],
    )

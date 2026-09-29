from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.employee_auth import assert_caller_is_employee, require_employee_session
from app.schemas.capability import CapabilityRead
from app.schemas.capability_evaluation import CapabilityEvaluationRead, EvaluateMissionAttemptRequest
from app.schemas.capability_evidence import CapabilityEvidenceRead
from app.schemas.capability_profile import CapabilityProfileRead
from app.schemas.development_journey import DevelopmentJourneyResponse
from app.schemas.quest import EmployeeQuestResponse
from app.schemas.recommendation import (
    CapabilityGapAnalysisResponse,
    NextMissionResponse,
    NextQuestResponse,
)
from app.schemas.readiness import EmployeeReadinessSummary
from app.schemas.workspace_access import EmployeeWorkspaceAccess
from app.services import (
    ai_evaluation_service,
    capability_service,
    development_journey,
    employee_service,
    mission_attempt_service,
    mission_recommendation,
    mission_service,
    quest_service,
    readiness_service,
    recommendation_persistence,
    workspace_access_service,
)
from app.services.ai_evaluation_service import AIEvaluationRejected
from app.services.ai_provider import AIProviderError

router = APIRouter(tags=["capabilities"])


@router.get("/capabilities", response_model=list[CapabilityRead])
async def list_capabilities(db: AsyncSession = Depends(get_db)):
    return await capability_service.list_capabilities(db)


@router.get("/employees/{employee_id}/capabilities", response_model=list[CapabilityProfileRead])
async def get_employee_capabilities(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(require_employee_session),
):
    assert_caller_is_employee(employee_id, session_employee_id)
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return await capability_service.list_profiles_for_employee(db, employee_id)


@router.get(
    "/employees/{employee_id}/capabilities/evidence", response_model=list[CapabilityEvidenceRead]
)
async def get_employee_capability_evidence(
    employee_id: str,
    capability_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(require_employee_session),
):
    assert_caller_is_employee(employee_id, session_employee_id)
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return await capability_service.list_evidence_for_employee(db, employee_id, capability_id)


async def _get_owned_attempt(db: AsyncSession, attempt_id: str, employee_id: str):
    """Never trust the frontend's attempt/employee pairing — the attempt's
    own employee_id (set server-side when the attempt was created) is the
    only thing that decides ownership."""
    attempt = await mission_attempt_service.get_attempt_by_id(db, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Mission attempt not found")
    if attempt.employee_id != employee_id:
        raise HTTPException(status_code=403, detail="This attempt does not belong to this employee")
    return attempt


@router.get("/mission-attempts/{attempt_id}/evaluation", response_model=CapabilityEvaluationRead | None)
async def get_mission_attempt_evaluation(
    attempt_id: str,
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(require_employee_session),
):
    assert_caller_is_employee(employee_id, session_employee_id)
    await _get_owned_attempt(db, attempt_id, employee_id)
    return await ai_evaluation_service.get_evaluation_for_attempt(db, attempt_id)


@router.post("/mission-attempts/{attempt_id}/evaluate", response_model=CapabilityEvaluationRead)
async def evaluate_mission_attempt(
    attempt_id: str,
    payload: EvaluateMissionAttemptRequest,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(require_employee_session),
):
    assert_caller_is_employee(payload.employee_id, session_employee_id)
    attempt = await _get_owned_attempt(db, attempt_id, payload.employee_id)
    if attempt.status != "completed":
        raise HTTPException(
            status_code=409, detail="This mission attempt has not been completed yet"
        )

    employee = await employee_service.get_employee(db, payload.employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    mission = await mission_service.get_mission(db, attempt.mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission.workspace_type == "quiz":
        # Deliberately no AI step for a quiz — see Mission.workspace_type's
        # own docstring: a multiple-choice pass/fail has nothing left for
        # a qualitative reader to add on top.
        raise HTTPException(
            status_code=409, detail="This mission is graded automatically and has no AI evaluation step"
        )

    try:
        return await ai_evaluation_service.evaluate_attempt(db, employee, mission, attempt)
    except AIProviderError as exc:
        # The employee's completed mission is untouched — only the AI
        # interpretation is unavailable right now. Recoverable: the
        # frontend should offer a retry, not surface this as a failure.
        raise HTTPException(status_code=503, detail=f"Buddy is still analyzing — try again shortly. ({exc})") from exc
    except AIEvaluationRejected as exc:
        raise HTTPException(status_code=502, detail=f"AI evaluation could not be validated: {exc}") from exc


@router.get("/employees/{employee_id}/next-mission", response_model=NextMissionResponse)
async def get_next_mission(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(require_employee_session),
):
    assert_caller_is_employee(employee_id, session_employee_id)
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    result = await mission_recommendation.get_next_mission(db, employee_id)
    return NextMissionResponse(
        mission=result.mission, reason=result.reason, target_capabilities=result.target_capabilities
    )


def _gap_items(items) -> list[dict]:
    return [
        {
            "capability": i.capability_key,
            "capability_name": i.capability_name,
            "current_level": i.current_level,
            "category": i.category,
            "reason": i.reason,
        }
        for i in items
    ]


@router.get("/employees/{employee_id}/next-quest", response_model=NextQuestResponse)
async def get_next_quest(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(require_employee_session),
):
    """Phase 6C's deterministic adaptive ranking (quest_recommendation.py,
    unchanged) wrapped by Phase 6D's persistence layer
    (recommendation_persistence.py): repeated calls with unchanged
    capability state reuse the same historical Recommendation row rather
    than writing a new one on every GET, and `reason`/`target_capabilities`
    in the response come from that persisted row, not a freshly-worded
    recomputation. `recommended_quest` is built from EmployeeQuestResponse
    — the same structurally employee-safe schema the Quest Workspace
    itself uses — so there is no code path here that could leak
    expected_answer/expected_behavior/reference_solution/evaluation
    criteria internals."""
    assert_caller_is_employee(employee_id, session_employee_id)
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    result = await recommendation_persistence.get_or_persist_next_quest(db, employee)

    recommended_quest = None
    if result.quest is not None:
        quest_with_content = await quest_service.get_quest_with_content(db, result.quest.id)
        # Phase 8H-3: required_for_readiness is independent of
        # recommendation selection — result.quest was already chosen by
        # quest_recommendation.py's unmodified ranking above; this only
        # enriches its serialization with a signal from the same
        # eligibility query is_ready() uses, computed separately.
        required_ids = await readiness_service.required_eligible_quest_ids(db, employee)
        recommended_quest = EmployeeQuestResponse.model_validate(quest_with_content).model_copy(
            update={"required_for_readiness": quest_with_content.id in required_ids}
        )

    gap_analysis = None
    if result.gap_analysis is not None:
        g = result.gap_analysis
        gap_analysis = CapabilityGapAnalysisResponse(
            employee_id=g.employee_id,
            strengths=_gap_items(g.strengths),
            development_areas=_gap_items(g.development_areas),
            unobserved=_gap_items(g.unobserved),
            assessed_capabilities=_gap_items(g.assessed_capabilities),
            generated_at=g.generated_at,
        )

    return NextQuestResponse(
        recommended_quest=recommended_quest,
        reason=result.reason,
        target_capabilities=result.target_capabilities,
        gap_analysis=gap_analysis,
    )


@router.get(
    "/employees/{employee_id}/development-journey", response_model=DevelopmentJourneyResponse
)
async def get_development_journey(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(require_employee_session),
):
    """Phase 6D — a deterministic, chronologically-ordered, employee-safe
    read model composed from four existing authoritative sources
    (OnboardingSession, completed QuestAttempts, CapabilityEvidence, and
    persisted Recommendation history). See
    services/development_journey.py for the ordering rule and what each
    item type is built from. Nothing here can carry
    expected_answer/expected_behavior/reference_solution, raw AI
    responses, or any other evaluator-only field — those models are
    never read by this endpoint's call chain at all."""
    assert_caller_is_employee(employee_id, session_employee_id)
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return await development_journey.build_journey(db, employee)


@router.get("/employees/{employee_id}/workspace-access", response_model=EmployeeWorkspaceAccess)
async def get_employee_workspace_access(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(require_employee_session),
):
    """Phase 8E — the employee-safe read of their department workspace's
    access state. Deliberately never triggers anything (no readiness
    check, no provider call, no grant creation) — it only reports what
    already exists. See workspace_access_service.get_employee_access and
    schemas/workspace_access.py's EmployeeWorkspaceAccess/
    WORKSPACE_ACCESS_API_STATUSES for the full status contract."""
    assert_caller_is_employee(employee_id, session_employee_id)
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return await workspace_access_service.get_employee_access(db, employee)


@router.get("/employees/{employee_id}/readiness-summary", response_model=EmployeeReadinessSummary)
async def get_employee_readiness_summary(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(require_employee_session),
):
    """Phase 8H-1 — the employee-safe readiness read model. Always
    derived fresh from current OnboardingSession/QuestAssignment/
    QuestAttempt state; never triggers anything (no workspace-access
    call, no side effects) and never stores anything. See
    readiness_service.get_readiness_summary for the full contract."""
    assert_caller_is_employee(employee_id, session_employee_id)
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return await readiness_service.get_readiness_summary(db, employee)

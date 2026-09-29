from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.admin_auth import require_admin_session
from app.core.employee_auth import assert_caller_is_employee, get_optional_employee_session
from app.schemas.ai_evaluation import AIEvaluationResponse
from app.schemas.quest import (
    EmployeeQuestResponse,
    EmployeeQuestSummary,
    QuestCreate,
    QuestDetailResponse,
    QuestQualityValidationResponse,
    QuestResponse,
    QuestUpdate,
)
from app.schemas.quest_assignment import QuestEligibilityResponse
from app.schemas.quest_attempt import (
    QuestAttemptCreate,
    QuestAttemptResponse,
    QuestAttemptSubmit,
    QuestAttemptUpdate,
)
from app.schemas.quest_evaluation import EvaluateQuestAttemptRequest, QuestEvaluationEmployeeResponse
from app.services import (
    employee_service,
    quest_assignment_service,
    quest_attempt_service,
    quest_evaluation_service,
    quest_quality_service,
    quest_service,
    readiness_service,
)
from app.services.ai_evaluation_service import AIEvaluationRejected
from app.services.ai_provider import AIProviderError
from app.services.quest_attempt_service import (
    IncompleteWorkSubmissionError,
    QuestAttemptAlreadyFinalizedError,
    RequiredTasksIncompleteError,
)
from app.services.quest_evaluation_service import QuestAttemptNotEvaluableError
from app.services.quest_service import QuestLifecycleError, QuestNotEditableError, QuestNotPublishableError

router = APIRouter(tags=["quests"])

# This router is mixed: manager-authoring endpoints (create/list/detail/
# update/publish/archive/publish-readiness) alongside employee-facing
# ones (eligibility, the employee-safe quest read, and everything under
# quest-attempts). Only the former get the login gate — applied per
# route below, not at the router level (see app/api/v1/router.py's own
# comment on why this router isn't in its wholesale admin-only list).
_admin = [Depends(require_admin_session)]


@router.post("/quests", response_model=QuestResponse, status_code=201, dependencies=_admin)
async def create_quest(payload: QuestCreate, db: AsyncSession = Depends(get_db)):
    return await quest_service.create_quest(db, payload)


@router.get("/quests", response_model=list[QuestResponse], dependencies=_admin)
async def list_quests(department_id: str | None = None, db: AsyncSession = Depends(get_db)):
    return await quest_service.list_quests(db, department_id)


@router.get("/quests/{quest_id}", response_model=QuestResponse, dependencies=_admin)
async def get_quest(quest_id: str, db: AsyncSession = Depends(get_db)):
    quest = await quest_service.get_quest(db, quest_id)
    if quest is None:
        raise HTTPException(status_code=404, detail="Quest not found")
    return quest


@router.patch("/quests/{quest_id}", response_model=QuestResponse, dependencies=_admin)
async def update_quest(quest_id: str, payload: QuestUpdate, db: AsyncSession = Depends(get_db)):
    """Basic-info edits are blocked once the quest is no longer DRAFT —
    see QuestNotEditableError (Stage 6A §23)."""
    quest = await quest_service.get_quest(db, quest_id)
    if quest is None:
        raise HTTPException(status_code=404, detail="Quest not found")
    try:
        quest_service.assert_quest_editable(quest)
    except QuestNotEditableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return await quest_service.update_quest(db, quest, payload)


@router.get(
    "/quests/{quest_id}/publish-readiness", response_model=QuestQualityValidationResponse, dependencies=_admin
)
async def get_quest_publish_readiness(quest_id: str, db: AsyncSession = Depends(get_db)):
    """The manager Builder's Quest Quality panel (Phase 6B) — purely
    informational for the UI; POST .../publish independently re-runs the
    same validation and remains authoritative regardless of what this
    returned."""
    quest = await quest_service.get_quest(db, quest_id)
    if quest is None:
        raise HTTPException(status_code=404, detail="Quest not found")
    return await quest_quality_service.validate_quest(db, quest)


@router.get("/quests/{quest_id}/detail", response_model=QuestDetailResponse, dependencies=_admin)
async def get_quest_detail(quest_id: str, db: AsyncSession = Depends(get_db)):
    """Manager/server-side view: tasks, evidence, evaluation criteria
    (including hidden expected_answer/expected_behavior/reference_solution),
    and capability mappings, all in one fetch. Never use this for an
    employee-facing response — see EmployeeQuestResponse (schemas/quest.py),
    not yet wired to any route (Stage 4)."""
    quest = await quest_service.get_quest_with_content(db, quest_id)
    if quest is None:
        raise HTTPException(status_code=404, detail="Quest not found")
    return quest


@router.post("/quests/{quest_id}/publish", response_model=QuestResponse, dependencies=_admin)
async def publish_quest(quest_id: str, db: AsyncSession = Depends(get_db)):
    """DRAFT -> PUBLISHED, only with at least one active assignment. A
    dedicated operation, not a PATCH — see schemas/quest.py's QuestUpdate,
    which no longer accepts a `status` field at all."""
    quest = await quest_service.get_quest(db, quest_id)
    if quest is None:
        raise HTTPException(status_code=404, detail="Quest not found")
    try:
        return await quest_service.publish_quest(db, quest)
    except QuestLifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QuestNotPublishableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/quests/{quest_id}/archive", response_model=QuestResponse, dependencies=_admin)
async def archive_quest(quest_id: str, db: AsyncSession = Depends(get_db)):
    """PUBLISHED -> ARCHIVED only."""
    quest = await quest_service.get_quest(db, quest_id)
    if quest is None:
        raise HTTPException(status_code=404, detail="Quest not found")
    try:
        return await quest_service.archive_quest(db, quest)
    except QuestLifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/quests/{quest_id}/eligibility/{employee_id}", response_model=QuestEligibilityResponse
)
async def get_quest_eligibility(
    quest_id: str,
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(get_optional_employee_session),
):
    """Access-eligibility only — never evaluation criteria or any other
    hidden Quest content (see QuestEligibilityResponse)."""
    assert_caller_is_employee(employee_id, session_employee_id)
    quest = await quest_service.get_quest(db, quest_id)
    if quest is None:
        raise HTTPException(status_code=404, detail="Quest not found")
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    result = await quest_assignment_service.is_employee_eligible(db, quest, employee)
    return QuestEligibilityResponse(
        eligible=result.eligible,
        quest_status=quest.status,
        matching_assignment_types=result.matching_assignment_types,
    )


@router.get("/quests/{quest_id}/employee", response_model=EmployeeQuestResponse)
async def get_employee_quest(
    quest_id: str,
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(get_optional_employee_session),
):
    """The employee-safe Quest Workspace contract (Stage 2's
    EmployeeQuestResponse, wired to a real route for the first time).
    Structurally incapable of returning evaluation criteria — the
    response_model itself has no field that could carry them, regardless
    of what get_quest_with_content loads. Re-checks eligibility
    independently of the /eligibility endpoint (the frontend calls that
    first for nuanced messaging, but this endpoint stays authoritative on
    its own — it must never trust that the frontend checked first)."""
    assert_caller_is_employee(employee_id, session_employee_id)
    quest = await quest_service.get_quest(db, quest_id)
    if quest is None:
        raise HTTPException(status_code=404, detail="Quest not found")
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    eligibility = await quest_assignment_service.is_employee_eligible(db, quest, employee)
    if not eligibility.eligible:
        raise HTTPException(status_code=403, detail="This quest is not available to you")

    quest_with_content = await quest_service.get_quest_with_content(db, quest_id)
    # Phase 8H-3: overlay the derived required_for_readiness signal —
    # never part of what quest_with_content itself carries, and
    # computed from the exact same eligibility query is_ready() uses,
    # not a second one.
    required_ids = await readiness_service.required_eligible_quest_ids(db, employee)
    response = EmployeeQuestResponse.model_validate(quest_with_content)
    return response.model_copy(update={"required_for_readiness": quest_with_content.id in required_ids})


@router.get("/employees/{employee_id}/quests", response_model=list[EmployeeQuestSummary])
async def list_employee_quests(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(get_optional_employee_session),
):
    """Phase 8H-4 — the employee's own Quest list (the previously-missing
    discovery surface the launch audit flagged: before this, a Quest was
    only reachable by already knowing its ID). Read-only: builds its
    answer from three existing, unchanged reads —
    quest_assignment_service.list_eligible_quest_ids_for_employee (the
    same matching rule the single-Quest eligibility check already uses),
    readiness_service.required_eligible_quest_ids (Phase 8H-3, unchanged),
    and quest_attempt_service.list_attempts_for_employee — and never
    calls get_or_create_attempt, so merely viewing this list can never
    create a QuestAttempt row."""
    assert_caller_is_employee(employee_id, session_employee_id)
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    eligible_ids = await quest_assignment_service.list_eligible_quest_ids_for_employee(db, employee)
    if not eligible_ids:
        return []

    quests = await quest_service.list_quests_by_ids(db, eligible_ids)
    required_ids = await readiness_service.required_eligible_quest_ids(db, employee)
    attempts = await quest_attempt_service.list_attempts_for_employee(db, employee_id)
    attempt_status_by_quest = {a.quest_id: a.status for a in attempts}

    return [
        EmployeeQuestSummary.model_validate(quest).model_copy(
            update={
                "required_for_readiness": quest.id in required_ids,
                "attempt_status": attempt_status_by_quest.get(quest.id),
            }
        )
        for quest in quests
    ]


@router.post("/quest-attempts", response_model=QuestAttemptResponse, status_code=201)
async def create_quest_attempt(
    payload: QuestAttemptCreate,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(get_optional_employee_session),
):
    """Eligibility is now enforced here, not just existence — knowing a
    quest_id is no longer enough to start an attempt on it (Stage 3
    spec §11). A quest that isn't PUBLISHED is a lifecycle problem (409);
    a PUBLISHED quest the employee isn't assigned to is an authorization
    problem (403) — both routed through
    quest_assignment_service.is_employee_eligible, the single
    authoritative eligibility check."""
    assert_caller_is_employee(payload.employee_id, session_employee_id)
    quest = await quest_service.get_quest(db, payload.quest_id)
    if quest is None:
        raise HTTPException(status_code=404, detail="Quest not found")
    employee = await employee_service.get_employee(db, payload.employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    if quest.status != "PUBLISHED":
        raise HTTPException(status_code=409, detail="This quest is not currently published")

    eligibility = await quest_assignment_service.is_employee_eligible(db, quest, employee)
    if not eligibility.eligible:
        raise HTTPException(status_code=403, detail="This employee is not eligible for this quest")

    return await quest_attempt_service.get_or_create_attempt(db, payload.quest_id, payload.employee_id)


@router.get("/quest-attempts/{attempt_id}", response_model=QuestAttemptResponse)
async def get_quest_attempt(
    attempt_id: str,
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(get_optional_employee_session),
):
    """`employee_id` is now required and checked against ownership (Stage
    4 spec §24) — previously this endpoint returned any attempt by id
    with no ownership check at all. This project has no session-based
    auth, so the caller-supplied employee_id is what's compared; the
    important guarantee is that it must match the attempt's own
    employee_id, not that the caller is cryptographically who they claim."""
    assert_caller_is_employee(employee_id, session_employee_id)
    attempt = await quest_attempt_service.get_attempt_by_id(db, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Quest attempt not found")
    if attempt.employee_id != employee_id:
        raise HTTPException(status_code=403, detail="This attempt does not belong to this employee")
    return attempt


@router.patch("/quest-attempts/{attempt_id}", response_model=QuestAttemptResponse)
async def update_quest_attempt(
    attempt_id: str,
    payload: QuestAttemptUpdate,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(get_optional_employee_session),
):
    """Autosave. Rejects once the attempt is SUBMITTED/COMPLETED (409) —
    a submitted quest must not silently become editable again."""
    assert_caller_is_employee(payload.employee_id, session_employee_id)
    attempt = await quest_attempt_service.get_attempt_by_id(db, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Quest attempt not found")
    if attempt.employee_id != payload.employee_id:
        raise HTTPException(status_code=403, detail="This attempt does not belong to this employee")

    try:
        return await quest_attempt_service.update_submission(db, attempt, payload)
    except QuestAttemptAlreadyFinalizedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/quest-attempts/{attempt_id}/submit", response_model=QuestAttemptResponse)
async def submit_quest_attempt(
    attempt_id: str,
    payload: QuestAttemptSubmit,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(get_optional_employee_session),
):
    """Re-validates the full eligibility chain at submit time, not just
    ownership — eligibility can change between starting and submitting
    (e.g. the quest gets archived, or the assignment is removed) and the
    server must catch that regardless of what the employee already did."""
    assert_caller_is_employee(payload.employee_id, session_employee_id)
    attempt = await quest_attempt_service.get_attempt_by_id(db, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Quest attempt not found")
    if attempt.employee_id != payload.employee_id:
        raise HTTPException(status_code=403, detail="This attempt does not belong to this employee")

    quest = await quest_service.get_quest(db, attempt.quest_id)
    if quest is None:
        raise HTTPException(status_code=404, detail="Quest not found")
    if quest.status != "PUBLISHED":
        raise HTTPException(status_code=409, detail="This quest is not currently published")

    employee = await employee_service.get_employee(db, payload.employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    eligibility = await quest_assignment_service.is_employee_eligible(db, quest, employee)
    if not eligibility.eligible:
        raise HTTPException(status_code=403, detail="This employee is not eligible for this quest")

    try:
        return await quest_attempt_service.submit_attempt(db, attempt, attempt.quest_id)
    except QuestAttemptAlreadyFinalizedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RequiredTasksIncompleteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IncompleteWorkSubmissionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _build_employee_evaluation_response(attempt, evaluation) -> QuestEvaluationEmployeeResponse:
    """Builds the employee-safe response from the validated
    structured_result only — never raw_response, never anything from
    QuestEvaluationCriterion. `attempt.status` is included so the
    frontend can distinguish EVALUATING from COMPLETED without a second
    round trip."""
    structured = AIEvaluationResponse.model_validate(evaluation.structured_result)
    return QuestEvaluationEmployeeResponse(
        status=attempt.status,
        summary=structured.summary,
        strengths=structured.strengths,
        development_areas=structured.development_areas,
        capabilities=structured.capabilities,
        recommended_focus=structured.recommended_focus,
        evaluated_at=evaluation.created_at,
    )


@router.get(
    "/quest-attempts/{attempt_id}/evaluation", response_model=QuestEvaluationEmployeeResponse | None
)
async def get_quest_attempt_evaluation(
    attempt_id: str,
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(get_optional_employee_session),
):
    """Returns null if no evaluation exists yet — either evaluation
    hasn't been triggered, or the quest has no capability mappings at
    all (a deterministic-only completion; see NoCapabilityMappingError).
    Never reveals whether a *different* employee's attempt exists: an
    ownership mismatch and a genuinely missing attempt both surface as
    404/403 the same way any other quest-attempt endpoint does."""
    assert_caller_is_employee(employee_id, session_employee_id)
    attempt = await quest_attempt_service.get_attempt_by_id(db, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Quest attempt not found")
    if attempt.employee_id != employee_id:
        raise HTTPException(status_code=403, detail="This attempt does not belong to this employee")

    evaluation = await quest_evaluation_service.get_evaluation_for_quest_attempt(db, attempt_id)
    if evaluation is None:
        return None
    return _build_employee_evaluation_response(attempt, evaluation)


@router.post(
    "/quest-attempts/{attempt_id}/evaluate", response_model=QuestEvaluationEmployeeResponse | None
)
async def evaluate_quest_attempt(
    attempt_id: str,
    payload: EvaluateQuestAttemptRequest,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(get_optional_employee_session),
):
    """Runs the full deterministic -> AI -> CapabilityEvidence ->
    CapabilityProfile pipeline (quest_evaluation_service.evaluate_attempt).
    On AI failure the attempt is returned to SUBMITTED — the employee's
    submitted work is never lost, and evaluation can be retried by
    calling this endpoint again."""
    assert_caller_is_employee(payload.employee_id, session_employee_id)
    attempt = await quest_attempt_service.get_attempt_by_id(db, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Quest attempt not found")
    if attempt.employee_id != payload.employee_id:
        raise HTTPException(status_code=403, detail="This attempt does not belong to this employee")

    quest = await quest_service.get_quest(db, attempt.quest_id)
    if quest is None:
        raise HTTPException(status_code=404, detail="Quest not found")
    employee = await employee_service.get_employee(db, payload.employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    try:
        evaluation = await quest_evaluation_service.evaluate_attempt(db, employee, quest, attempt)
    except QuestAttemptNotEvaluableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AIProviderError as exc:
        raise HTTPException(
            status_code=503, detail=f"Buddy is still analyzing — try again shortly. ({exc})"
        ) from exc
    except AIEvaluationRejected as exc:
        raise HTTPException(status_code=502, detail=f"AI evaluation could not be validated: {exc}") from exc

    if evaluation is None:
        return None
    return _build_employee_evaluation_response(attempt, evaluation)

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.employee_auth import assert_caller_is_employee, require_employee_session
from app.schemas.mission_attempt import (
    MissionAttemptCreate,
    MissionAttemptRead,
    MissionAttemptSubmit,
    MissionAttemptUpdate,
    MissionQuizRead,
    MissionScenarioRead,
)
from app.services import mission_attempt_service, mission_service

router = APIRouter(tags=["mission-attempts"])


async def _assert_owns_mission(db: AsyncSession, mission_id: str, employee_id: str):
    """Never trust the frontend's mission_id/employee_id pairing — verify a
    real mission_assignment exists before allowing any attempt to start."""
    mission = await mission_service.get_mission(db, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")

    assignment = await mission_service.get_assignment_for_employee_mission(db, mission_id, employee_id)
    if assignment is None:
        raise HTTPException(status_code=403, detail="This mission is not assigned to this employee")

    return mission


@router.get("/missions/{mission_id}/scenario", response_model=MissionScenarioRead)
async def get_mission_scenario(
    mission_id: str,
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(require_employee_session),
):
    assert_caller_is_employee(employee_id, session_employee_id)
    mission = await _assert_owns_mission(db, mission_id, employee_id)
    scenario = await mission_attempt_service.get_public_scenario(db, mission)
    if scenario is None:
        raise HTTPException(status_code=404, detail="This mission has no investigation workspace")
    return scenario


@router.get("/missions/{mission_id}/quiz", response_model=MissionQuizRead)
async def get_mission_quiz(
    mission_id: str,
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(require_employee_session),
):
    assert_caller_is_employee(employee_id, session_employee_id)
    mission = await _assert_owns_mission(db, mission_id, employee_id)
    quiz = await mission_attempt_service.get_public_quiz(db, mission)
    if quiz is None:
        raise HTTPException(status_code=404, detail="This mission has no quiz workspace")
    return quiz


@router.get("/mission-attempts", response_model=MissionAttemptRead)
async def get_mission_attempt(
    mission_id: str,
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(require_employee_session),
):
    assert_caller_is_employee(employee_id, session_employee_id)
    await _assert_owns_mission(db, mission_id, employee_id)
    attempt = await mission_attempt_service.get_attempt(db, mission_id, employee_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="No attempt started for this mission yet")
    return attempt


@router.post("/mission-attempts", response_model=MissionAttemptRead, status_code=201)
async def create_mission_attempt(
    payload: MissionAttemptCreate,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(require_employee_session),
):
    assert_caller_is_employee(payload.employee_id, session_employee_id)
    await _assert_owns_mission(db, payload.mission_id, payload.employee_id)
    return await mission_attempt_service.get_or_create_attempt(
        db, payload.mission_id, payload.employee_id
    )


@router.patch("/mission-attempts/{attempt_id}", response_model=MissionAttemptRead)
async def update_mission_attempt(
    attempt_id: str,
    payload: MissionAttemptUpdate,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(require_employee_session),
):
    attempt = await mission_attempt_service.get_attempt_by_id(db, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Mission attempt not found")
    # P5 — Production Security Hardening. This handler's own
    # MissionAttemptUpdate payload has no employee_id field at all, so
    # there was previously no ownership check of any kind here —
    # checked against the attempt's own already-loaded employee_id,
    # the one piece of "whose attempt is this" this endpoint has ever
    # had, rather than adding a new required request field.
    assert_caller_is_employee(attempt.employee_id, session_employee_id)
    if attempt.status in ("completed",):
        raise HTTPException(status_code=409, detail="This mission is already completed")
    return await mission_attempt_service.update_attempt(db, attempt, payload)


@router.post("/mission-attempts/{attempt_id}/submit", response_model=MissionAttemptRead)
async def submit_mission_attempt(
    attempt_id: str,
    payload: MissionAttemptSubmit,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(require_employee_session),
):
    attempt = await mission_attempt_service.get_attempt_by_id(db, attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Mission attempt not found")
    if attempt.employee_id != payload.employee_id:
        raise HTTPException(status_code=403, detail="This attempt does not belong to this employee")
    assert_caller_is_employee(payload.employee_id, session_employee_id)
    if attempt.status == "completed":
        raise HTTPException(status_code=409, detail="This mission is already completed")

    mission = await mission_service.get_mission(db, attempt.mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")

    # workspace_type-specific requirements (a scenario for investigation,
    # real answers for quiz) are validated inside submit_attempt's own
    # branch, not here — this endpoint no longer needs to know which
    # workspace kind a given Mission uses at all.
    return await mission_attempt_service.submit_attempt(db, attempt, mission, payload)

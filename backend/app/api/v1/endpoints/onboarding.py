from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.admin_auth import require_admin_session
from app.core.config import get_settings
from app.core.employee_auth import assert_caller_is_employee, get_current_employee, require_employee_session
from app.models import Employee
from app.schemas.assessment import AssessmentRead, AssessmentSubmit
from app.schemas.onboarding_bundle import OnboardingBundle
from app.schemas.onboarding_session import OnboardingSessionRead, OnboardingSessionUpdate
from app.services import assessment_service, employee_service, onboarding_service

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/bundle/me", response_model=OnboardingBundle)
async def get_my_bundle(
    employee: Employee = Depends(get_current_employee), db: AsyncSession = Depends(get_db)
):
    """P1 — Identity & Invitation Foundation. The production path: the
    employee is derived from their authenticated session (see
    core/employee_auth.py), never from a client-supplied id. This is
    what a genuine invitation-exchange flow resolves onboarding through;
    `/bundle/demo` below remains the zero-auth path for the existing
    single-hardcoded-identity demo environment."""
    return await onboarding_service.build_bundle(db, employee)


@router.get("/bundle/demo", response_model=OnboardingBundle)
async def get_demo_bundle(db: AsyncSession = Depends(get_db)):
    """Bootstraps the MVP demo identity from server-side config. No
    caller-supplied identifier selects whose data comes back, so this
    cannot be used to enumerate other employees' data."""
    settings = get_settings()
    employee = await employee_service.get_employee_by_email(db, settings.demo_employee_email)
    if employee is None:
        raise HTTPException(status_code=404, detail="Demo employee not configured")
    return await onboarding_service.build_bundle(db, employee)


@router.post("/demo/reset", response_model=OnboardingBundle)
async def reset_demo(db: AsyncSession = Depends(get_db)):
    """Demo/presentation tooling only — puts the demo employee's onboarding
    back to day one (scene, missions, Quest attempts, assessment,
    workspace access all cleared) so the same environment can be run
    through a live demo repeatedly. Resolves the employee exactly like
    GET /bundle/demo does: no caller-supplied identifier, so this can
    never reset anyone else's onboarding."""
    settings = get_settings()
    employee = await employee_service.get_employee_by_email(db, settings.demo_employee_email)
    if employee is None:
        raise HTTPException(status_code=404, detail="Demo employee not configured")
    await onboarding_service.reset_onboarding_progress(db, employee)
    return await onboarding_service.build_bundle(db, employee)


@router.get(
    "/bundle/{employee_id}",
    response_model=OnboardingBundle,
    dependencies=[Depends(require_admin_session)],
)
async def get_bundle(employee_id: str, db: AsyncSession = Depends(get_db)):
    """P1 — Identity & Invitation Foundation. Previously open to any
    caller who supplied an employee_id, with no authentication at all —
    a cross-employee data exposure the P0 architecture audit flagged as
    a Critical gap. Now admin-only (manager/support lookup of a specific
    employee's bundle); the employee-facing equivalent is `/bundle/me`
    above, which derives the employee from the caller's own session and
    can never be pointed at someone else's data."""
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return await onboarding_service.build_bundle(db, employee)


@router.patch("/sessions/{session_id}", response_model=OnboardingSessionRead)
async def update_session(
    session_id: str,
    payload: OnboardingSessionUpdate,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(require_employee_session),
):
    """P5.1 — Production Employee Authorization Hardening. This route
    has no `employee_id` param at all (it's addressed by session_id),
    so ownership is checked against the loaded OnboardingSession's own
    `employee_id` — the same "load first, then compare" pattern
    mission_attempts.py's `update_mission_attempt` already established
    for the identical shape of gap."""
    session = await onboarding_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
    assert_caller_is_employee(session.employee_id, session_employee_id)
    return await onboarding_service.update_session(db, session, payload)


@router.post("/assessments", response_model=AssessmentRead, status_code=201)
async def submit_assessment(
    payload: AssessmentSubmit,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(require_employee_session),
):
    assert_caller_is_employee(payload.employee_id, session_employee_id)
    return await assessment_service.submit_assessment(db, payload)


@router.get("/assessments/{session_id}", response_model=AssessmentRead)
async def get_assessment(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    session_employee_id: str | None = Depends(require_employee_session),
):
    assessment = await assessment_service.get_by_session(db, session_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    assert_caller_is_employee(assessment.employee_id, session_employee_id)
    return assessment

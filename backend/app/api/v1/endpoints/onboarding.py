from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.schemas.assessment import AssessmentRead, AssessmentSubmit
from app.schemas.onboarding_bundle import OnboardingBundle
from app.schemas.onboarding_session import OnboardingSessionRead, OnboardingSessionUpdate
from app.services import assessment_service, employee_service, onboarding_service

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


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


@router.get("/bundle/by-token/{session_token}", response_model=OnboardingBundle)
async def get_bundle_by_token(session_token: str, db: AsyncSession = Depends(get_db)):
    """Looks up a bundle by onboarding session id, used as an opaque access
    token — the basis for a future personalized onboarding link, in place
    of treating an employee's email as if it were a secret."""
    bundle = await onboarding_service.get_bundle_by_session_token(db, session_token)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
    return bundle


@router.get("/bundle/{employee_id}", response_model=OnboardingBundle)
async def get_bundle(employee_id: str, db: AsyncSession = Depends(get_db)):
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return await onboarding_service.build_bundle(db, employee)


@router.patch("/sessions/{session_id}", response_model=OnboardingSessionRead)
async def update_session(
    session_id: str, payload: OnboardingSessionUpdate, db: AsyncSession = Depends(get_db)
):
    session = await onboarding_service.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Onboarding session not found")
    return await onboarding_service.update_session(db, session, payload)


@router.post("/assessments", response_model=AssessmentRead, status_code=201)
async def submit_assessment(payload: AssessmentSubmit, db: AsyncSession = Depends(get_db)):
    return await assessment_service.submit_assessment(db, payload)


@router.get("/assessments/{session_id}", response_model=AssessmentRead)
async def get_assessment(session_id: str, db: AsyncSession = Depends(get_db)):
    assessment = await assessment_service.get_by_session(db, session_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return assessment

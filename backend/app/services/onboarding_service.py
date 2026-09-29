from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    SCENES,
    Assessment,
    Employee,
    MissionAssignment,
    MissionAttempt,
    OnboardingSession,
    QuestAttempt,
    WorkspaceAccessGrant,
)
from app.schemas.onboarding_session import OnboardingSessionUpdate
from app.services import (
    department_service,
    employee_service,
    mission_service,
    organization_service,
    project_service,
    role_service,
)
from app.services.assessment_questions import ASSESSMENT_QUESTIONS


def scene_progress(scene: str) -> int:
    if scene not in SCENES:
        return 0
    return round((SCENES.index(scene) / (len(SCENES) - 1)) * 100)


async def get_or_create_session(db: AsyncSession, employee: Employee) -> tuple[OnboardingSession, bool]:
    """Read-only for an existing session in the common case. Only
    provisions missions the one time a session is first created — never
    on a repeated read, so a plain GET can never write mission_assignment
    rows (build_bundle below relies on this).

    Returns `(session, created)`. The `created` flag exists for
    provisioning_service's reporting — it is not a correctness signal
    anything else here depends on.

    Race-safe as of P2: `uq_onboarding_session_employee` (a real
    database constraint, not just this function's own SELECT-then-check)
    means two callers racing to create the first session for the same
    employee — e.g. eager provisioning called concurrently — can't both
    succeed. The loser's insert raises IntegrityError; it recovers by
    re-reading the winner's row rather than raising, so callers never
    have to handle this race themselves.
    """
    result = await db.execute(
        select(OnboardingSession).where(OnboardingSession.employee_id == employee.id)
    )
    session = result.scalars().first()
    if session:
        return session, False

    session = OnboardingSession(
        employee_id=employee.id,
        current_scene="welcome",
        status="in_progress",
        progress_percent=scene_progress("welcome"),
        started_at=datetime.now(timezone.utc),
    )
    db.add(session)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        result = await db.execute(
            select(OnboardingSession).where(OnboardingSession.employee_id == employee.id)
        )
        session = result.scalars().first()
        if session is None:
            raise
        return session, False
    await db.refresh(session)

    if employee.department_id:
        await mission_service.ensure_assignments_for_employee(
            db, employee.id, employee.department_id, session.id
        )

    return session, True


async def reset_onboarding_progress(db: AsyncSession, employee: Employee) -> OnboardingSession:
    """Demo/presentation tooling — puts one employee's onboarding back to
    day one so the same environment can be run through a live demo
    repeatedly. Never wired to a client-suppliable employee_id (see the
    `/onboarding/demo/reset` endpoint, which resolves the employee the
    same server-side-only way `/onboarding/bundle/demo` does); a real
    multi-tenant deployment would not expose an unauthenticated "erase my
    onboarding history" action at all.

    Puts every row this employee's onboarding touches back to the shape
    get_or_create_session would produce for a brand-new employee: the
    session itself reset in place (not deleted, so its id/URL stay
    stable), mission assignments reset to pending rather than
    re-provisioned (avoids duplicating rows against the same unique
    constraint get_or_create_assignments relies on), and every derived
    attempt/grant record removed outright so Quest evaluation, the
    Assessment, and workspace access are all genuinely fresh — not left
    pointing at stale results.
    """
    result = await db.execute(
        select(OnboardingSession).where(OnboardingSession.employee_id == employee.id)
    )
    session = result.scalars().first()
    if session is None:
        return await get_or_create_session(db, employee)

    session.current_scene = "welcome"
    session.status = "in_progress"
    session.progress_percent = scene_progress("welcome")
    session.started_at = datetime.now(timezone.utc)
    session.completed_at = None

    assignments = (
        await db.execute(
            select(MissionAssignment).where(MissionAssignment.employee_id == employee.id)
        )
    ).scalars().all()
    for assignment in assignments:
        assignment.status = "pending"
        assignment.completed_at = None

    for model in (MissionAttempt, Assessment, QuestAttempt, WorkspaceAccessGrant):
        rows = (await db.execute(select(model).where(model.employee_id == employee.id))).scalars().all()
        for row in rows:
            await db.delete(row)

    await db.commit()
    await db.refresh(session)
    return session


async def update_session(
    db: AsyncSession, session: OnboardingSession, payload: OnboardingSessionUpdate
) -> OnboardingSession:
    if payload.current_scene is not None:
        session.current_scene = payload.current_scene
        session.progress_percent = scene_progress(payload.current_scene)
        if payload.current_scene == "completion":
            session.status = "completed"
            session.completed_at = datetime.now(timezone.utc)
    if payload.status is not None:
        session.status = payload.status

    await db.commit()
    await db.refresh(session)
    return session


async def get_session(db: AsyncSession, session_id: str) -> OnboardingSession | None:
    return await db.get(OnboardingSession, session_id)


async def build_bundle(db: AsyncSession, employee: Employee) -> dict:
    """Read-only: assembles the bundle from existing rows. Mission
    provisioning happens once, in get_or_create_session, never here — so
    repeated calls (e.g. GET /onboarding/bundle/{id}) never write."""
    session, _created = await get_or_create_session(db, employee)

    organization = await organization_service.get_organization(db, employee.organization_id)
    department = await department_service.get_department(db, employee.department_id) if employee.department_id else None
    role = await role_service.get_role(db, employee.role_id) if employee.role_id else None
    manager = await employee_service.get_employee(db, employee.manager_id) if employee.manager_id else None
    supervisor = (
        await employee_service.get_employee(db, employee.supervisor_id) if employee.supervisor_id else None
    )
    teammates = (
        await employee_service.get_teammates(db, employee.department_id, employee.id)
        if employee.department_id
        else []
    )
    projects = await project_service.list_projects(db, employee.department_id) if employee.department_id else []

    mission_assignments = await mission_service.list_assignments_for_employee(db, employee.id)

    return {
        "employee": employee,
        "organization": organization,
        "department": department,
        "role": role,
        "manager": manager,
        "supervisor": supervisor,
        "teammates": teammates,
        "projects": projects,
        "session": session,
        "mission_assignments": mission_assignments,
        "assessment_questions": ASSESSMENT_QUESTIONS,
    }

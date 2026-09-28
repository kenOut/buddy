from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Mission, MissionAssignment
from app.schemas.mission import MissionCreate, MissionUpdate
from app.services import readiness_service


async def list_missions(db: AsyncSession, department_id: str | None = None) -> list[Mission]:
    stmt = select(Mission).order_by(Mission.sort_order)
    if department_id:
        stmt = stmt.where(Mission.department_id == department_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_mission(db: AsyncSession, mission_id: str) -> Mission | None:
    return await db.get(Mission, mission_id)


async def create_mission(db: AsyncSession, payload: MissionCreate) -> Mission:
    mission = Mission(**payload.model_dump())
    db.add(mission)
    await db.commit()
    await db.refresh(mission)
    return mission


async def update_mission(db: AsyncSession, mission: Mission, payload: MissionUpdate) -> Mission:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(mission, field, value)
    await db.commit()
    await db.refresh(mission)
    return mission


async def list_assignments_for_employee(db: AsyncSession, employee_id: str) -> list[MissionAssignment]:
    stmt = (
        select(MissionAssignment)
        .where(MissionAssignment.employee_id == employee_id)
        .options(selectinload(MissionAssignment.mission))
        .order_by(MissionAssignment.assigned_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def ensure_assignments_for_employee(
    db: AsyncSession, employee_id: str, department_id: str, onboarding_session_id: str
) -> list[MissionAssignment]:
    """Idempotently assign every department mission to an employee's session."""
    existing = await list_assignments_for_employee(db, employee_id)
    existing_mission_ids = {a.mission_id for a in existing}

    missions = await list_missions(db, department_id=department_id)
    created = False
    for mission in missions:
        if mission.id not in existing_mission_ids:
            db.add(
                MissionAssignment(
                    mission_id=mission.id,
                    employee_id=employee_id,
                    onboarding_session_id=onboarding_session_id,
                    status="pending",
                )
            )
            created = True

    if created:
        await db.commit()
        existing = await list_assignments_for_employee(db, employee_id)

    return existing


async def get_assignment_for_employee_mission(
    db: AsyncSession, mission_id: str, employee_id: str
) -> MissionAssignment | None:
    """Used to verify a mission actually belongs to this employee before
    letting them start or act on a mission attempt — never trust the
    frontend's mission_id/employee_id pairing on its own."""
    stmt = select(MissionAssignment).where(
        MissionAssignment.mission_id == mission_id,
        MissionAssignment.employee_id == employee_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_assignment(db: AsyncSession, assignment_id: str) -> MissionAssignment | None:
    stmt = (
        select(MissionAssignment)
        .where(MissionAssignment.id == assignment_id)
        .options(selectinload(MissionAssignment.mission))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_assignment_status(
    db: AsyncSession, assignment: MissionAssignment, status: str
) -> MissionAssignment:
    assignment.status = status
    assignment.completed_at = datetime.now(timezone.utc) if status == "completed" else None
    await db.commit()
    await db.refresh(assignment)

    if status == "completed":
        # Single choke point for both Mission completion paths (the
        # "simple" mission's own PATCH and the investigation flow's
        # submit_attempt, which both funnel through this function) — see
        # readiness_service.check_and_trigger's own docstring for why
        # this only ever runs after the row above is durably committed,
        # and why it can never surface as a failure of this call.
        await readiness_service.check_and_trigger(assignment.employee_id)

    return assignment

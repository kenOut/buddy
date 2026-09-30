from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Mission, MissionAssignment, MissionAttempt
from app.schemas.mission import MissionCreate, MissionUpdate
from app.services import mission_quizzes, mission_scenarios, readiness_service


class MissingWorkspaceContentError(Exception):
    """Raised when a quiz/investigation Mission's title has no matching
    entry in mission_quizzes.py/mission_scenarios.py — those workspace
    types are static, server-side-only content keyed by exact title
    string (see either module's own docstring for why: seeded mission
    ids aren't stable across reseeds). Letting a mismatched title
    through would create a Mission that 404s for every employee who
    opens it — caught here instead, at creation/update time, not
    discovered later by an employee."""


class MissionHasAttemptsError(Exception):
    """Raised when deleting a Mission that at least one employee has
    already attempted. Mirrors the Employee "deactivate, never delete"
    precedent in this codebase: MissionAttempt/CapabilityEvidence rows
    are historical work product, and SQLite never enforces this
    project's `ondelete="CASCADE"` FK pragmas (see mission.py's
    `assignments` relationship comment), so a hard delete here would
    either orphan that history or silently destroy it — neither is
    acceptable. A Mission with no attempts yet (the realistic "remove a
    stale/misconfigured mission" case) has nothing to protect and
    deletes cleanly, cascading only its own MissionAssignment rows."""


def _assert_workspace_content_exists(workspace_type: str, title: str) -> None:
    if workspace_type == "quiz" and title not in mission_quizzes.MISSION_QUIZZES:
        raise MissingWorkspaceContentError(
            f'No quiz content exists for the title "{title}" in mission_quizzes.py.'
        )
    if workspace_type == "investigation" and title not in mission_scenarios.MISSION_SCENARIOS:
        raise MissingWorkspaceContentError(
            f'No investigation scenario exists for the title "{title}" in mission_scenarios.py.'
        )


async def list_missions(db: AsyncSession, department_id: str | None = None) -> list[Mission]:
    stmt = select(Mission).order_by(Mission.sort_order)
    if department_id:
        stmt = stmt.where(Mission.department_id == department_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_mission(db: AsyncSession, mission_id: str) -> Mission | None:
    return await db.get(Mission, mission_id)


async def create_mission(db: AsyncSession, payload: MissionCreate) -> Mission:
    _assert_workspace_content_exists(payload.workspace_type, payload.title)
    mission = Mission(**payload.model_dump())
    db.add(mission)
    await db.commit()
    await db.refresh(mission)
    return mission


async def update_mission(db: AsyncSession, mission: Mission, payload: MissionUpdate) -> Mission:
    fields = payload.model_dump(exclude_unset=True)
    workspace_type = fields.get("workspace_type", mission.workspace_type)
    title = fields.get("title", mission.title)
    _assert_workspace_content_exists(workspace_type, title)

    for field, value in fields.items():
        setattr(mission, field, value)
    await db.commit()
    await db.refresh(mission)
    return mission


async def delete_mission(db: AsyncSession, mission: Mission) -> None:
    attempt_count_result = await db.execute(
        select(MissionAttempt.id).where(MissionAttempt.mission_id == mission.id).limit(1)
    )
    if attempt_count_result.scalar_one_or_none() is not None:
        raise MissionHasAttemptsError(
            "This mission has already been attempted by at least one employee and can't be deleted."
        )
    await db.delete(mission)
    await db.commit()


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

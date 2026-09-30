from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Department,
    Employee,
    Mission,
    Project,
    Quest,
    QuestAssignment,
    Role,
    WorkspaceIntegration,
)
from app.schemas.department import DepartmentCreate, DepartmentUpdate


class DepartmentHasEmployeesError(Exception):
    """Raised when deleting a Department that still has employees
    assigned to it. Mirrors mission_service.MissionHasAttemptsError's
    reasoning: Employee.department_id is SET NULL, nullable — deleting
    the department wouldn't fail, it would silently strip every one of
    those employees of their department (breaking their onboarding
    missions, readiness, and org-chart placement) as a side effect of
    what looks like an unrelated cleanup action. A department with real
    people in it needs them moved out first (the existing per-employee
    department dropdown on the Employees page already does this), not
    an implicit mass-unassignment. An empty department has nothing to
    protect and deletes — along with its own roles/teams/projects/
    workspace integration — cleanly."""


async def list_departments(db: AsyncSession, organization_id: str | None = None) -> list[Department]:
    stmt = select(Department).order_by(Department.name)
    if organization_id:
        stmt = stmt.where(Department.organization_id == organization_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_department(db: AsyncSession, department_id: str) -> Department | None:
    return await db.get(Department, department_id)


async def create_department(db: AsyncSession, payload: DepartmentCreate) -> Department:
    department = Department(
        organization_id=payload.organization_id,
        name=payload.name,
        description=payload.description,
    )
    db.add(department)
    await db.commit()
    await db.refresh(department)
    return department


async def update_department(db: AsyncSession, department: Department, payload: DepartmentUpdate) -> Department:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(department, field, value)
    await db.commit()
    await db.refresh(department)
    return department


async def delete_department(db: AsyncSession, department: Department) -> None:
    employee_result = await db.execute(
        select(Employee.id).where(Employee.department_id == department.id).limit(1)
    )
    if employee_result.scalar_one_or_none() is not None:
        raise DepartmentHasEmployeesError(
            "This department still has employees assigned to it. Move them to another "
            "department before deleting it."
        )

    role_ids_result = await db.execute(select(Role.id).where(Role.department_id == department.id))
    role_ids = list(role_ids_result.scalars().all())

    project_ids_result = await db.execute(
        select(Project.id).where(Project.department_id == department.id)
    )
    project_ids = list(project_ids_result.scalars().all())

    # Every relationship below declares its own ondelete pragma at the DB
    # level, but SQLite (this project's dev/test database) never
    # enforces those — see mission.py's `assignments` relationship
    # comment for the same gotcha. Each statement here does by hand what
    # the declared pragma promises: SET NULL for content that survives
    # detached from this department, CASCADE (delete) for rows that are
    # only meaningful while attached to it.
    if role_ids:
        await db.execute(update(Employee).where(Employee.role_id.in_(role_ids)).values(role_id=None))
    if project_ids:
        await db.execute(update(Mission).where(Mission.project_id.in_(project_ids)).values(project_id=None))
        await db.execute(update(Quest).where(Quest.project_id.in_(project_ids)).values(project_id=None))

    await db.execute(update(Mission).where(Mission.department_id == department.id).values(department_id=None))
    await db.execute(update(Quest).where(Quest.department_id == department.id).values(department_id=None))

    assignment_filter = QuestAssignment.department_id == department.id
    if role_ids:
        assignment_filter = assignment_filter | QuestAssignment.role_id.in_(role_ids)
    await db.execute(delete(QuestAssignment).where(assignment_filter))

    await db.execute(delete(WorkspaceIntegration).where(WorkspaceIntegration.department_id == department.id))
    await db.execute(delete(Project).where(Project.department_id == department.id))
    await db.execute(delete(Role).where(Role.department_id == department.id))

    # Teams cascade via the ORM relationship itself (Department.teams'
    # cascade="all, delete-orphan", added in Phase A for this exact
    # reason).
    await db.delete(department)
    await db.commit()

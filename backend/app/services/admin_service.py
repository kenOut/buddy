from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Department, Employee, MissionAssignment, OnboardingSession
from app.services import mission_service


async def get_overview(db: AsyncSession) -> dict:
    employees = list((await db.execute(select(Employee))).scalars().all())
    departments = list((await db.execute(select(Department))).scalars().all())
    department_by_id = {d.id: d for d in departments}

    sessions = list((await db.execute(select(OnboardingSession))).scalars().all())
    session_by_employee = {s.employee_id: s for s in sessions}

    in_progress = sum(1 for s in sessions if s.status == "in_progress")
    completed = sum(1 for s in sessions if s.status == "completed")

    rows = []
    for employee in employees:
        session = session_by_employee.get(employee.id)
        assignments: list[MissionAssignment] = await mission_service.list_assignments_for_employee(
            db, employee.id
        )
        rows.append(
            {
                "employee": employee,
                "department": department_by_id.get(employee.department_id),
                "session": session,
                "missions_completed": sum(1 for a in assignments if a.status == "completed"),
                "missions_total": len(assignments),
            }
        )

    return {
        "total_employees": len(employees),
        "onboarding_in_progress": in_progress,
        "onboarding_completed": completed,
        "total_departments": len(departments),
        "rows": rows,
    }

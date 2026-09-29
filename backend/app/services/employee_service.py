from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee


async def list_employees(db: AsyncSession, department_id: str | None = None) -> list[Employee]:
    stmt = select(Employee).order_by(Employee.full_name)
    if department_id:
        stmt = stmt.where(Employee.department_id == department_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_employee(db: AsyncSession, employee_id: str) -> Employee | None:
    return await db.get(Employee, employee_id)


async def get_employee_by_email(db: AsyncSession, email: str) -> Employee | None:
    result = await db.execute(select(Employee).where(Employee.email == email))
    return result.scalar_one_or_none()


async def get_teammates(db: AsyncSession, department_id: str, exclude_employee_id: str) -> list[Employee]:
    stmt = (
        select(Employee)
        .where(Employee.department_id == department_id)
        .where(Employee.id != exclude_employee_id)
        .order_by(Employee.full_name)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_employee_status(db: AsyncSession, employee: Employee, status: str) -> Employee:
    employee.status = status
    await db.commit()
    await db.refresh(employee)
    return employee


async def update_employee_department(
    db: AsyncSession, employee: Employee, department_id: str | None
) -> Employee:
    employee.department_id = department_id
    await db.commit()
    await db.refresh(employee)
    return employee


async def update_employee_avatar(db: AsyncSession, employee: Employee, avatar_url: str) -> Employee:
    employee.avatar_url = avatar_url
    await db.commit()
    await db.refresh(employee)
    return employee

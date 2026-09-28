from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Department
from app.schemas.department import DepartmentCreate


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

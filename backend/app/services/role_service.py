from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Role
from app.schemas.role import RoleCreate


async def list_roles(db: AsyncSession, department_id: str | None = None) -> list[Role]:
    stmt = select(Role).order_by(Role.title)
    if department_id:
        stmt = stmt.where(Role.department_id == department_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_role(db: AsyncSession, role_id: str) -> Role | None:
    return await db.get(Role, role_id)


async def create_role(db: AsyncSession, payload: RoleCreate) -> Role:
    role = Role(
        department_id=payload.department_id,
        title=payload.title,
        level=payload.level,
        description=payload.description,
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role

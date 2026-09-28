from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project
from app.schemas.project import ProjectCreate


async def list_projects(db: AsyncSession, department_id: str | None = None) -> list[Project]:
    stmt = select(Project).order_by(Project.name)
    if department_id:
        stmt = stmt.where(Project.department_id == department_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_project(db: AsyncSession, project_id: str) -> Project | None:
    return await db.get(Project, project_id)


async def create_project(db: AsyncSession, payload: ProjectCreate) -> Project:
    project = Project(
        department_id=payload.department_id,
        name=payload.name,
        description=payload.description,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project

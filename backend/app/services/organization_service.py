from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Organization
from app.schemas.organization import OrganizationCreate


async def list_organizations(db: AsyncSession) -> list[Organization]:
    result = await db.execute(select(Organization).order_by(Organization.name))
    return list(result.scalars().all())


async def get_organization(db: AsyncSession, organization_id: str) -> Organization | None:
    return await db.get(Organization, organization_id)


async def create_organization(db: AsyncSession, payload: OrganizationCreate) -> Organization:
    org = Organization(name=payload.name, slug=payload.slug)
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org

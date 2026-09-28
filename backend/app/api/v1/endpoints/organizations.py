from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.organization import OrganizationCreate, OrganizationRead
from app.services import organization_service

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("", response_model=list[OrganizationRead])
async def list_organizations(db: AsyncSession = Depends(get_db)):
    return await organization_service.list_organizations(db)


@router.post("", response_model=OrganizationRead, status_code=201)
async def create_organization(payload: OrganizationCreate, db: AsyncSession = Depends(get_db)):
    return await organization_service.create_organization(db, payload)

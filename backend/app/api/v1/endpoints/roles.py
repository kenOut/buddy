from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.role import RoleCreate, RoleRead
from app.services import role_service

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=list[RoleRead])
async def list_roles(department_id: str | None = None, db: AsyncSession = Depends(get_db)):
    return await role_service.list_roles(db, department_id)


@router.get("/{role_id}", response_model=RoleRead)
async def get_role(role_id: str, db: AsyncSession = Depends(get_db)):
    role = await role_service.get_role(db, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


@router.post("", response_model=RoleRead, status_code=201)
async def create_role(payload: RoleCreate, db: AsyncSession = Depends(get_db)):
    return await role_service.create_role(db, payload)

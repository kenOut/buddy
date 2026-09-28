from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.mission import MissionCreate, MissionRead, MissionUpdate
from app.services import mission_service

router = APIRouter(tags=["missions"])


@router.get("/missions", response_model=list[MissionRead])
async def list_missions(department_id: str | None = None, db: AsyncSession = Depends(get_db)):
    return await mission_service.list_missions(db, department_id)


@router.get("/missions/{mission_id}", response_model=MissionRead)
async def get_mission(mission_id: str, db: AsyncSession = Depends(get_db)):
    mission = await mission_service.get_mission(db, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


@router.post("/missions", response_model=MissionRead, status_code=201)
async def create_mission(payload: MissionCreate, db: AsyncSession = Depends(get_db)):
    return await mission_service.create_mission(db, payload)


@router.patch("/missions/{mission_id}", response_model=MissionRead)
async def update_mission(mission_id: str, payload: MissionUpdate, db: AsyncSession = Depends(get_db)):
    """Admin-only in practice (no employee-facing client ever calls this)
    — same trust level as create_mission above, which already accepts
    arbitrary Mission fields with no auth check of its own."""
    mission = await mission_service.get_mission(db, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return await mission_service.update_mission(db, mission, payload)

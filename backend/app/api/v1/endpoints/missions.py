from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.mission import MissionCreate, MissionRead, MissionUpdate
from app.services import mission_quizzes, mission_scenarios, mission_service
from app.services.mission_service import MissingWorkspaceContentError, MissionHasAttemptsError

router = APIRouter(tags=["missions"])


@router.get("/missions", response_model=list[MissionRead])
async def list_missions(department_id: str | None = None, db: AsyncSession = Depends(get_db)):
    return await mission_service.list_missions(db, department_id)


@router.get("/missions/workspace-content-titles", response_model=dict[str, list[str]])
async def get_workspace_content_titles():
    """The New Mission form (Manager Portal) needs this so an admin can
    only pick a title real content actually exists for, instead of
    typing a title free-hand and finding out it 404s for employees only
    after the mission is live — quiz/investigation Mission content is
    static and keyed by exact title string (mission_quizzes.py/
    mission_scenarios.py), not by mission_id, since seeded mission ids
    aren't stable across reseeds. Reflection needs no entry here since
    it has no title-keyed content to match."""
    return {
        "quiz": sorted(mission_quizzes.MISSION_QUIZZES.keys()),
        "investigation": sorted(mission_scenarios.MISSION_SCENARIOS.keys()),
    }


@router.get("/missions/{mission_id}", response_model=MissionRead)
async def get_mission(mission_id: str, db: AsyncSession = Depends(get_db)):
    mission = await mission_service.get_mission(db, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


@router.post("/missions", response_model=MissionRead, status_code=201)
async def create_mission(payload: MissionCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await mission_service.create_mission(db, payload)
    except MissingWorkspaceContentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/missions/{mission_id}", response_model=MissionRead)
async def update_mission(mission_id: str, payload: MissionUpdate, db: AsyncSession = Depends(get_db)):
    """Admin-only in practice (no employee-facing client ever calls this)
    — same trust level as create_mission above, which already accepts
    arbitrary Mission fields with no auth check of its own."""
    mission = await mission_service.get_mission(db, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    try:
        return await mission_service.update_mission(db, mission, payload)
    except MissingWorkspaceContentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/missions/{mission_id}", status_code=204)
async def delete_mission(mission_id: str, db: AsyncSession = Depends(get_db)):
    mission = await mission_service.get_mission(db, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    try:
        await mission_service.delete_mission(db, mission)
    except MissionHasAttemptsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models import Quest
from app.schemas.quest_capability import QuestCapabilityCreate, QuestCapabilityResponse
from app.services import capability_service, quest_capability_service, quest_service
from app.services.quest_capability_service import DuplicateQuestCapabilityError
from app.services.quest_service import QuestNotEditableError

router = APIRouter(tags=["quest-capabilities"])


async def _assert_quest_exists(db: AsyncSession, quest_id: str) -> None:
    quest = await quest_service.get_quest(db, quest_id)
    if quest is None:
        raise HTTPException(status_code=404, detail="Quest not found")


async def _assert_quest_editable(db: AsyncSession, quest_id: str) -> Quest:
    quest = await quest_service.get_quest(db, quest_id)
    if quest is None:
        raise HTTPException(status_code=404, detail="Quest not found")
    try:
        quest_service.assert_quest_editable(quest)
    except QuestNotEditableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return quest


@router.post(
    "/quests/{quest_id}/capabilities", response_model=QuestCapabilityResponse, status_code=201
)
async def create_capability_mapping(
    quest_id: str, payload: QuestCapabilityCreate, db: AsyncSession = Depends(get_db)
):
    await _assert_quest_editable(db, quest_id)
    capability = await capability_service.get_capability(db, payload.capability_id)
    if capability is None:
        raise HTTPException(status_code=404, detail="Capability not found")
    try:
        return await quest_capability_service.create_mapping(db, quest_id, payload)
    except DuplicateQuestCapabilityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/quests/{quest_id}/capabilities", response_model=list[QuestCapabilityResponse])
async def list_capability_mappings(quest_id: str, db: AsyncSession = Depends(get_db)):
    await _assert_quest_exists(db, quest_id)
    return await quest_capability_service.list_mappings(db, quest_id)


@router.delete("/quests/{quest_id}/capabilities/{capability_id}", status_code=204)
async def delete_capability_mapping(
    quest_id: str, capability_id: str, db: AsyncSession = Depends(get_db)
):
    await _assert_quest_editable(db, quest_id)
    mapping = await quest_capability_service.get_mapping_by_capability_id(db, quest_id, capability_id)
    if mapping is None:
        raise HTTPException(status_code=404, detail="Quest capability mapping not found")
    await quest_capability_service.delete_mapping(db, mapping)

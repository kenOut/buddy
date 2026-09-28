from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models import Quest
from app.schemas.quest_task import QuestTaskCreate, QuestTaskResponse, QuestTaskUpdate
from app.services import quest_service, quest_task_service
from app.services.quest_service import QuestNotEditableError

router = APIRouter(tags=["quest-tasks"])


async def _assert_quest_exists(db: AsyncSession, quest_id: str) -> None:
    quest = await quest_service.get_quest(db, quest_id)
    if quest is None:
        raise HTTPException(status_code=404, detail="Quest not found")


async def _assert_quest_editable(db: AsyncSession, quest_id: str) -> Quest:
    """Used by every mutating (POST/PATCH/DELETE) endpoint below — read
    endpoints stay available regardless of status, but content can only
    change while the quest is still DRAFT (Stage 6A §23)."""
    quest = await quest_service.get_quest(db, quest_id)
    if quest is None:
        raise HTTPException(status_code=404, detail="Quest not found")
    try:
        quest_service.assert_quest_editable(quest)
    except QuestNotEditableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return quest


@router.post("/quests/{quest_id}/tasks", response_model=QuestTaskResponse, status_code=201)
async def create_task(quest_id: str, payload: QuestTaskCreate, db: AsyncSession = Depends(get_db)):
    await _assert_quest_editable(db, quest_id)
    return await quest_task_service.create_task(db, quest_id, payload)


@router.get("/quests/{quest_id}/tasks", response_model=list[QuestTaskResponse])
async def list_tasks(quest_id: str, db: AsyncSession = Depends(get_db)):
    await _assert_quest_exists(db, quest_id)
    return await quest_task_service.list_tasks(db, quest_id)


@router.patch("/quests/{quest_id}/tasks/{task_id}", response_model=QuestTaskResponse)
async def update_task(
    quest_id: str, task_id: str, payload: QuestTaskUpdate, db: AsyncSession = Depends(get_db)
):
    await _assert_quest_editable(db, quest_id)
    task = await quest_task_service.get_task(db, quest_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Quest task not found")
    return await quest_task_service.update_task(db, task, payload)


@router.delete("/quests/{quest_id}/tasks/{task_id}", status_code=204)
async def delete_task(quest_id: str, task_id: str, db: AsyncSession = Depends(get_db)):
    await _assert_quest_editable(db, quest_id)
    task = await quest_task_service.get_task(db, quest_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Quest task not found")
    await quest_task_service.delete_task(db, task)

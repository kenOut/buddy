from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.quest_assignment import (
    QuestAssignmentCreate,
    QuestAssignmentResponse,
    QuestAssignmentUpdate,
)
from app.services import quest_assignment_service, quest_service
from app.services.quest_assignment_service import DuplicateQuestAssignmentError

router = APIRouter(tags=["quest-assignments"])


async def _assert_quest_exists(db: AsyncSession, quest_id: str) -> None:
    quest = await quest_service.get_quest(db, quest_id)
    if quest is None:
        raise HTTPException(status_code=404, detail="Quest not found")


@router.post(
    "/quests/{quest_id}/assignments", response_model=QuestAssignmentResponse, status_code=201
)
async def create_assignment(
    quest_id: str, payload: QuestAssignmentCreate, db: AsyncSession = Depends(get_db)
):
    await _assert_quest_exists(db, quest_id)
    try:
        return await quest_assignment_service.create_assignment(db, quest_id, payload)
    except DuplicateQuestAssignmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/quests/{quest_id}/assignments", response_model=list[QuestAssignmentResponse])
async def list_assignments(quest_id: str, db: AsyncSession = Depends(get_db)):
    await _assert_quest_exists(db, quest_id)
    return await quest_assignment_service.list_assignments(db, quest_id)


@router.get(
    "/quests/{quest_id}/assignments/{assignment_id}", response_model=QuestAssignmentResponse
)
async def get_assignment(quest_id: str, assignment_id: str, db: AsyncSession = Depends(get_db)):
    assignment = await quest_assignment_service.get_assignment(db, quest_id, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Quest assignment not found")
    return assignment


@router.patch(
    "/quests/{quest_id}/assignments/{assignment_id}", response_model=QuestAssignmentResponse
)
async def update_assignment(
    quest_id: str,
    assignment_id: str,
    payload: QuestAssignmentUpdate,
    db: AsyncSession = Depends(get_db),
):
    assignment = await quest_assignment_service.get_assignment(db, quest_id, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Quest assignment not found")
    return await quest_assignment_service.update_assignment(db, assignment, payload)


@router.delete("/quests/{quest_id}/assignments/{assignment_id}", status_code=204)
async def delete_assignment(quest_id: str, assignment_id: str, db: AsyncSession = Depends(get_db)):
    assignment = await quest_assignment_service.get_assignment(db, quest_id, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Quest assignment not found")
    await quest_assignment_service.delete_assignment(db, assignment)

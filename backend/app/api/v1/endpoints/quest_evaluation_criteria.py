"""Server-only content. Every response here is QuestEvaluationCriterionInternal
— never QuestEvidenceResponse/QuestTaskResponse's employee-safe shape, and
this router is never referenced from any employee-facing code path."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models import Quest
from app.schemas.quest_evaluation_criterion import (
    QuestEvaluationCriterionCreate,
    QuestEvaluationCriterionInternal,
    QuestEvaluationCriterionUpdate,
)
from app.services import quest_evaluation_criterion_service, quest_service
from app.services.quest_service import QuestNotEditableError

router = APIRouter(tags=["quest-evaluation-criteria"])


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
    "/quests/{quest_id}/evaluation-criteria",
    response_model=QuestEvaluationCriterionInternal,
    status_code=201,
)
async def create_criterion(
    quest_id: str, payload: QuestEvaluationCriterionCreate, db: AsyncSession = Depends(get_db)
):
    await _assert_quest_editable(db, quest_id)
    return await quest_evaluation_criterion_service.create_criterion(db, quest_id, payload)


@router.get(
    "/quests/{quest_id}/evaluation-criteria", response_model=list[QuestEvaluationCriterionInternal]
)
async def list_criteria(quest_id: str, db: AsyncSession = Depends(get_db)):
    await _assert_quest_exists(db, quest_id)
    return await quest_evaluation_criterion_service.list_criteria(db, quest_id)


@router.patch(
    "/quests/{quest_id}/evaluation-criteria/{criterion_id}",
    response_model=QuestEvaluationCriterionInternal,
)
async def update_criterion(
    quest_id: str,
    criterion_id: str,
    payload: QuestEvaluationCriterionUpdate,
    db: AsyncSession = Depends(get_db),
):
    await _assert_quest_editable(db, quest_id)
    criterion = await quest_evaluation_criterion_service.get_criterion(db, quest_id, criterion_id)
    if criterion is None:
        raise HTTPException(status_code=404, detail="Quest evaluation criterion not found")
    return await quest_evaluation_criterion_service.update_criterion(db, criterion, payload)


@router.delete("/quests/{quest_id}/evaluation-criteria/{criterion_id}", status_code=204)
async def delete_criterion(quest_id: str, criterion_id: str, db: AsyncSession = Depends(get_db)):
    await _assert_quest_editable(db, quest_id)
    criterion = await quest_evaluation_criterion_service.get_criterion(db, quest_id, criterion_id)
    if criterion is None:
        raise HTTPException(status_code=404, detail="Quest evaluation criterion not found")
    await quest_evaluation_criterion_service.delete_criterion(db, criterion)

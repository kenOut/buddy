from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models import Quest
from app.schemas.quest_evidence import QuestEvidenceCreate, QuestEvidenceResponse, QuestEvidenceUpdate
from app.services import quest_evidence_service, quest_service
from app.services.quest_service import QuestNotEditableError

router = APIRouter(tags=["quest-evidence"])


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


@router.post("/quests/{quest_id}/evidence", response_model=QuestEvidenceResponse, status_code=201)
async def create_evidence(quest_id: str, payload: QuestEvidenceCreate, db: AsyncSession = Depends(get_db)):
    await _assert_quest_editable(db, quest_id)
    return await quest_evidence_service.create_evidence(db, quest_id, payload)


@router.get("/quests/{quest_id}/evidence", response_model=list[QuestEvidenceResponse])
async def list_evidence(quest_id: str, db: AsyncSession = Depends(get_db)):
    await _assert_quest_exists(db, quest_id)
    return await quest_evidence_service.list_evidence(db, quest_id)


@router.patch("/quests/{quest_id}/evidence/{evidence_id}", response_model=QuestEvidenceResponse)
async def update_evidence(
    quest_id: str, evidence_id: str, payload: QuestEvidenceUpdate, db: AsyncSession = Depends(get_db)
):
    await _assert_quest_editable(db, quest_id)
    evidence = await quest_evidence_service.get_evidence(db, quest_id, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="Quest evidence not found")
    return await quest_evidence_service.update_evidence(db, evidence, payload)


@router.delete("/quests/{quest_id}/evidence/{evidence_id}", status_code=204)
async def delete_evidence(quest_id: str, evidence_id: str, db: AsyncSession = Depends(get_db)):
    await _assert_quest_editable(db, quest_id)
    evidence = await quest_evidence_service.get_evidence(db, quest_id, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="Quest evidence not found")
    await quest_evidence_service.delete_evidence(db, evidence)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QuestEvidence
from app.schemas.quest_evidence import QuestEvidenceCreate, QuestEvidenceUpdate


async def list_evidence(db: AsyncSession, quest_id: str) -> list[QuestEvidence]:
    stmt = (
        select(QuestEvidence)
        .where(QuestEvidence.quest_id == quest_id)
        .order_by(QuestEvidence.sort_order)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_evidence(db: AsyncSession, quest_id: str, evidence_id: str) -> QuestEvidence | None:
    """Scoped to `quest_id` — never a bare `db.get(QuestEvidence, evidence_id)`,
    so evidence belonging to a different quest can never be read or
    modified through this quest's URL."""
    stmt = select(QuestEvidence).where(
        QuestEvidence.id == evidence_id, QuestEvidence.quest_id == quest_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_evidence(db: AsyncSession, quest_id: str, payload: QuestEvidenceCreate) -> QuestEvidence:
    evidence = QuestEvidence(quest_id=quest_id, **payload.model_dump())
    db.add(evidence)
    await db.commit()
    await db.refresh(evidence)
    return evidence


async def update_evidence(
    db: AsyncSession, evidence: QuestEvidence, payload: QuestEvidenceUpdate
) -> QuestEvidence:
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(evidence, field, value)
    await db.commit()
    await db.refresh(evidence)
    return evidence


async def delete_evidence(db: AsyncSession, evidence: QuestEvidence) -> None:
    await db.delete(evidence)
    await db.commit()

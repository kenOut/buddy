"""Server-only content — see schemas/quest_evaluation_criterion.py. This
service is only ever called from manager/server-side endpoints; nothing
here is reachable from an employee-facing route."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QuestEvaluationCriterion
from app.schemas.quest_evaluation_criterion import (
    QuestEvaluationCriterionCreate,
    QuestEvaluationCriterionUpdate,
)


async def list_criteria(db: AsyncSession, quest_id: str) -> list[QuestEvaluationCriterion]:
    stmt = (
        select(QuestEvaluationCriterion)
        .where(QuestEvaluationCriterion.quest_id == quest_id)
        .order_by(QuestEvaluationCriterion.sort_order)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_criterion(
    db: AsyncSession, quest_id: str, criterion_id: str
) -> QuestEvaluationCriterion | None:
    """Scoped to `quest_id` — never a bare `db.get(...)`, so a criterion
    belonging to a different quest can never be read or modified through
    this quest's URL."""
    stmt = select(QuestEvaluationCriterion).where(
        QuestEvaluationCriterion.id == criterion_id, QuestEvaluationCriterion.quest_id == quest_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_criterion(
    db: AsyncSession, quest_id: str, payload: QuestEvaluationCriterionCreate
) -> QuestEvaluationCriterion:
    criterion = QuestEvaluationCriterion(quest_id=quest_id, **payload.model_dump())
    db.add(criterion)
    await db.commit()
    await db.refresh(criterion)
    return criterion


async def update_criterion(
    db: AsyncSession,
    criterion: QuestEvaluationCriterion,
    payload: QuestEvaluationCriterionUpdate,
) -> QuestEvaluationCriterion:
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(criterion, field, value)
    await db.commit()
    await db.refresh(criterion)
    return criterion


async def delete_criterion(db: AsyncSession, criterion: QuestEvaluationCriterion) -> None:
    await db.delete(criterion)
    await db.commit()

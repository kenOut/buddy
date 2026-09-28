from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import QuestCapability
from app.schemas.quest_capability import QuestCapabilityCreate


class DuplicateQuestCapabilityError(Exception):
    """Raised when a Quest already has a mapping for the given capability.
    Unlike QuestAttempt's get-or-create, a duplicate mapping is a genuine
    client error here (the manager tried to add the same capability
    twice), not something to silently resolve to the existing row."""


async def list_mappings(db: AsyncSession, quest_id: str) -> list[QuestCapability]:
    stmt = (
        select(QuestCapability)
        .where(QuestCapability.quest_id == quest_id)
        .options(selectinload(QuestCapability.capability))
        .order_by(QuestCapability.created_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_mapping(db: AsyncSession, quest_id: str, mapping_id: str) -> QuestCapability | None:
    """Scoped to `quest_id` — never a bare `db.get(...)`, so a mapping
    belonging to a different quest can never be read or deleted through
    this quest's URL."""
    stmt = (
        select(QuestCapability)
        .where(QuestCapability.id == mapping_id, QuestCapability.quest_id == quest_id)
        .options(selectinload(QuestCapability.capability))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_mapping_by_capability_id(
    db: AsyncSession, quest_id: str, capability_id: str
) -> QuestCapability | None:
    """Looked up by the underlying Capability's id, not the mapping's own
    id — matches DELETE /quests/{quest_id}/capabilities/{capability_id}
    ("remove this capability from this quest")."""
    stmt = select(QuestCapability).where(
        QuestCapability.quest_id == quest_id, QuestCapability.capability_id == capability_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_mapping(
    db: AsyncSession, quest_id: str, payload: QuestCapabilityCreate
) -> QuestCapability:
    mapping = QuestCapability(
        quest_id=quest_id, capability_id=payload.capability_id, weight=payload.weight
    )
    db.add(mapping)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateQuestCapabilityError(
            f"Quest {quest_id} already has a mapping for capability {payload.capability_id}"
        ) from exc
    await db.refresh(mapping, attribute_names=["capability"])
    return mapping


async def delete_mapping(db: AsyncSession, mapping: QuestCapability) -> None:
    await db.delete(mapping)
    await db.commit()

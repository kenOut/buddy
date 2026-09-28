from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QuestTask
from app.schemas.quest_task import QuestTaskCreate, QuestTaskUpdate


async def list_tasks(db: AsyncSession, quest_id: str) -> list[QuestTask]:
    stmt = select(QuestTask).where(QuestTask.quest_id == quest_id).order_by(QuestTask.sort_order)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_task(db: AsyncSession, quest_id: str, task_id: str) -> QuestTask | None:
    """Scoped to `quest_id` — never a bare `db.get(QuestTask, task_id)`, so
    a task belonging to a different quest can never be read or modified
    through this quest's URL."""
    stmt = select(QuestTask).where(QuestTask.id == task_id, QuestTask.quest_id == quest_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_task(db: AsyncSession, quest_id: str, payload: QuestTaskCreate) -> QuestTask:
    task = QuestTask(quest_id=quest_id, **payload.model_dump())
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def update_task(db: AsyncSession, task: QuestTask, payload: QuestTaskUpdate) -> QuestTask:
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(task, field, value)
    await db.commit()
    await db.refresh(task)
    return task


async def delete_task(db: AsyncSession, task: QuestTask) -> None:
    await db.delete(task)
    await db.commit()

from datetime import datetime

from pydantic import field_validator

from app.models.quest_task import TASK_TYPES
from app.schemas.common import ORMBase


class QuestTaskCreate(ORMBase):
    title: str
    description: str | None = None
    task_type: str
    sort_order: int = 0
    required: bool = True

    @field_validator("task_type")
    @classmethod
    def _valid_task_type(cls, v: str) -> str:
        if v not in TASK_TYPES:
            raise ValueError(f"task_type must be one of {TASK_TYPES}")
        return v


class QuestTaskUpdate(ORMBase):
    title: str | None = None
    description: str | None = None
    task_type: str | None = None
    sort_order: int | None = None
    required: bool | None = None

    @field_validator("task_type")
    @classmethod
    def _valid_task_type(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in TASK_TYPES:
            raise ValueError(f"task_type must be one of {TASK_TYPES}")
        return v


class QuestTaskResponse(ORMBase):
    """Employee-visible by definition — this is the work itself, so this
    schema is safe to embed in both manager and employee-facing Quest
    representations (see schemas/quest.py)."""

    id: str
    quest_id: str
    title: str
    description: str | None
    task_type: str
    sort_order: int
    required: bool
    created_at: datetime
    updated_at: datetime

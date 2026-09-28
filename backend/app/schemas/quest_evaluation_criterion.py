"""Server-only. Nothing in this module is ever imported into an
employee-facing schema (contrast schemas/quest_task.py and
schemas/quest_evidence.py, whose response models ARE reused in
EmployeeQuestResponse — see schemas/quest.py). The class name
`QuestEvaluationCriterionInternal` is deliberately not `...Response`, so a
future author reaching for "the Quest evaluation-criterion schema" is
signaled, by the name itself, that it's the manager/server side."""

from datetime import datetime

from pydantic import field_validator

from app.models.quest_evaluation_criterion import CRITERION_TYPES
from app.schemas.common import ORMBase


class QuestEvaluationCriterionCreate(ORMBase):
    name: str
    description: str | None = None
    criterion_type: str
    expected_answer: str | None = None
    expected_behavior: str | None = None
    reference_solution: str | None = None
    max_score: float = 100
    sort_order: int = 0

    @field_validator("criterion_type")
    @classmethod
    def _valid_criterion_type(cls, v: str) -> str:
        if v not in CRITERION_TYPES:
            raise ValueError(f"criterion_type must be one of {CRITERION_TYPES}")
        return v

    @field_validator("max_score")
    @classmethod
    def _valid_max_score(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("max_score must be greater than 0")
        return v


class QuestEvaluationCriterionUpdate(ORMBase):
    name: str | None = None
    description: str | None = None
    criterion_type: str | None = None
    expected_answer: str | None = None
    expected_behavior: str | None = None
    reference_solution: str | None = None
    max_score: float | None = None
    sort_order: int | None = None

    @field_validator("criterion_type")
    @classmethod
    def _valid_criterion_type(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in CRITERION_TYPES:
            raise ValueError(f"criterion_type must be one of {CRITERION_TYPES}")
        return v

    @field_validator("max_score")
    @classmethod
    def _valid_max_score(cls, v: float | None) -> float | None:
        if v is None:
            return v
        if v <= 0:
            raise ValueError("max_score must be greater than 0")
        return v


class QuestEvaluationCriterionInternal(ORMBase):
    """Server-only representation — expected_answer/expected_behavior/
    reference_solution are exactly the hidden evaluation content that must
    never reach an employee. Use only from manager/server-side endpoints."""

    id: str
    quest_id: str
    name: str
    description: str | None
    criterion_type: str
    expected_answer: str | None
    expected_behavior: str | None
    reference_solution: str | None
    max_score: float
    sort_order: int
    created_at: datetime
    updated_at: datetime

    @field_validator("criterion_type")
    @classmethod
    def _valid_criterion_type(cls, v: str) -> str:
        if v not in CRITERION_TYPES:
            raise ValueError(f"criterion_type must be one of {CRITERION_TYPES}")
        return v

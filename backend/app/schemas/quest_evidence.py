from datetime import datetime

from pydantic import field_validator

from app.models.quest_evidence import EVIDENCE_TYPES
from app.schemas.common import JSONValue, ORMBase


class QuestEvidenceCreate(ORMBase):
    title: str
    description: str | None = None
    evidence_type: str
    content: dict[str, JSONValue] = {}
    sort_order: int = 0

    @field_validator("evidence_type")
    @classmethod
    def _valid_evidence_type(cls, v: str) -> str:
        if v not in EVIDENCE_TYPES:
            raise ValueError(f"evidence_type must be one of {EVIDENCE_TYPES}")
        return v


class QuestEvidenceUpdate(ORMBase):
    title: str | None = None
    description: str | None = None
    evidence_type: str | None = None
    content: dict[str, JSONValue] | None = None
    sort_order: int | None = None

    @field_validator("evidence_type")
    @classmethod
    def _valid_evidence_type(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in EVIDENCE_TYPES:
            raise ValueError(f"evidence_type must be one of {EVIDENCE_TYPES}")
        return v


class QuestEvidenceResponse(ORMBase):
    """Employee-visible by definition — this schema is safe to embed in
    both manager and employee-facing Quest representations (see
    schemas/quest.py). QuestEvidence never carries hidden/answer-key
    content; that lives exclusively in QuestEvaluationCriterion, which has
    its own, deliberately separate schema module."""

    id: str
    quest_id: str
    title: str
    description: str | None
    evidence_type: str
    content: dict[str, JSONValue]
    sort_order: int
    created_at: datetime
    updated_at: datetime

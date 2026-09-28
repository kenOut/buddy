from datetime import datetime

from pydantic import field_validator

from app.models.capability_evidence import EVIDENCE_SOURCES, EVIDENCE_STRENGTHS
from app.schemas.common import ORMBase


class CapabilityEvidenceRead(ORMBase):
    id: str
    employee_id: str
    mission_attempt_id: str | None
    quest_attempt_id: str | None
    capability_id: str
    evaluation_id: str | None

    evidence_type: str
    observation: str
    strength: str
    confidence: float
    source: str

    created_at: datetime

    @field_validator("strength")
    @classmethod
    def _valid_strength(cls, v: str) -> str:
        if v not in EVIDENCE_STRENGTHS:
            raise ValueError(f"strength must be one of {EVIDENCE_STRENGTHS}")
        return v

    @field_validator("source")
    @classmethod
    def _valid_source(cls, v: str) -> str:
        if v not in EVIDENCE_SOURCES:
            raise ValueError(f"source must be one of {EVIDENCE_SOURCES}")
        return v

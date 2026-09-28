from datetime import datetime

from pydantic import field_validator

from app.models.capability_profile import CAPABILITY_LEVELS
from app.schemas.capability import CapabilityRead
from app.schemas.common import ORMBase


class CapabilityProfileRead(ORMBase):
    id: str
    employee_id: str
    capability_id: str
    capability: CapabilityRead

    level: str
    score: float
    confidence: float
    evidence_count: int

    updated_at: datetime

    @field_validator("level")
    @classmethod
    def _valid_level(cls, v: str) -> str:
        if v not in CAPABILITY_LEVELS:
            raise ValueError(f"level must be one of {CAPABILITY_LEVELS}")
        return v

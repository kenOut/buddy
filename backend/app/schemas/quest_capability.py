from datetime import datetime

from pydantic import field_validator

from app.schemas.capability import CapabilityRead
from app.schemas.common import ORMBase


class QuestCapabilityCreate(ORMBase):
    capability_id: str
    weight: float = 1.0

    @field_validator("weight")
    @classmethod
    def _valid_weight(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("weight must be greater than 0")
        return v


class QuestCapabilityResponse(ORMBase):
    id: str
    quest_id: str
    capability_id: str
    capability: CapabilityRead
    weight: float
    created_at: datetime

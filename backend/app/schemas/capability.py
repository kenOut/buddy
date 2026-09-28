from datetime import datetime

from app.schemas.common import ORMBase


class CapabilityRead(ORMBase):
    id: str
    key: str
    name: str
    description: str | None
    created_at: datetime

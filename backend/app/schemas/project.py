from datetime import datetime

from app.schemas.common import ORMBase


class ProjectCreate(ORMBase):
    department_id: str
    name: str
    description: str | None = None


class ProjectRead(ORMBase):
    id: str
    department_id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

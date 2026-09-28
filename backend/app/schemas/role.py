from datetime import datetime

from app.schemas.common import ORMBase


class RoleCreate(ORMBase):
    department_id: str
    title: str
    level: str | None = None
    description: str | None = None


class RoleRead(ORMBase):
    id: str
    department_id: str
    title: str
    level: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime

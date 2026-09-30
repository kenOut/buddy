from datetime import datetime

from app.schemas.common import ORMBase


class DepartmentCreate(ORMBase):
    organization_id: str
    name: str
    description: str | None = None


class DepartmentUpdate(ORMBase):
    name: str | None = None
    description: str | None = None


class DepartmentRead(ORMBase):
    id: str
    organization_id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

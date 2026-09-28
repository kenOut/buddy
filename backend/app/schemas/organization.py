from datetime import datetime

from app.schemas.common import ORMBase


class OrganizationCreate(ORMBase):
    name: str
    slug: str


class OrganizationRead(ORMBase):
    id: str
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime

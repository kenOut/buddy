from datetime import datetime

from pydantic import Field

from app.schemas.common import ORMBase


class TeamCreate(ORMBase):
    """`department_id` is deliberately absent — it comes from the URL
    path (POST /departments/{department_id}/teams), the same convention
    WorkspaceIntegrationCreate already uses for its own department_id."""

    name: str = Field(min_length=1)
    description: str | None = None


class TeamRead(ORMBase):
    id: str
    department_id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

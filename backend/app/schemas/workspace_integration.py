from datetime import datetime

from pydantic import ValidationInfo, field_validator

from app.models.workspace_integration import WORKSPACE_PROVIDERS
from app.schemas.common import ORMBase


class WorkspaceIntegrationCreate(ORMBase):
    """`department_id` is deliberately absent — it comes from the URL
    path (POST /departments/{department_id}/workspace), the same
    convention as QuestAssignmentCreate never carrying quest_id."""

    provider: str
    external_ref: str
    display_name: str
    workspace_link: str
    active: bool = True

    @field_validator("provider")
    @classmethod
    def _valid_provider(cls, v: str) -> str:
        if v not in WORKSPACE_PROVIDERS:
            raise ValueError(f"provider must be one of {WORKSPACE_PROVIDERS}")
        return v


class WorkspaceIntegrationUpdate(ORMBase):
    provider: str | None = None
    external_ref: str | None = None
    display_name: str | None = None
    workspace_link: str | None = None
    active: bool | None = None

    @field_validator("provider")
    @classmethod
    def _valid_provider(cls, v: str | None, info: ValidationInfo) -> str | None:
        if v is None:
            return v
        if v not in WORKSPACE_PROVIDERS:
            raise ValueError(f"provider must be one of {WORKSPACE_PROVIDERS}")
        return v


class WorkspaceIntegrationRead(ORMBase):
    """Manager/admin-facing — deliberately fuller than employee-safe
    EmployeeWorkspaceAccess (schemas/workspace_access.py): a manager who
    configured this row is exactly who `external_ref`/`provider` are
    *for*. Never returned from an employee-facing endpoint — those stay
    on EmployeeWorkspaceAccess."""

    id: str
    department_id: str
    provider: str
    external_ref: str
    display_name: str
    workspace_link: str
    active: bool
    created_at: datetime
    updated_at: datetime

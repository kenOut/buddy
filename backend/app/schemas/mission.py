from datetime import datetime

from app.schemas.common import ORMBase


class MissionCreate(ORMBase):
    project_id: str | None = None
    department_id: str | None = None
    title: str
    description: str | None = None
    mission_type: str = "task"
    estimated_minutes: int = 15
    sort_order: int = 0
    required: bool = False
    workspace_type: str = "reflection"


class MissionUpdate(ORMBase):
    title: str | None = None
    description: str | None = None
    mission_type: str | None = None
    estimated_minutes: int | None = None
    sort_order: int | None = None
    required: bool | None = None
    workspace_type: str | None = None


class MissionRead(ORMBase):
    id: str
    project_id: str | None
    department_id: str | None
    title: str
    description: str | None
    mission_type: str
    estimated_minutes: int
    sort_order: int
    required: bool
    workspace_type: str
    created_at: datetime
    updated_at: datetime


class MissionAssignmentRead(ORMBase):
    id: str
    mission_id: str
    employee_id: str
    onboarding_session_id: str | None
    status: str
    assigned_at: datetime
    completed_at: datetime | None
    mission: MissionRead

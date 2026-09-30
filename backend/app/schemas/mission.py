from datetime import datetime

from pydantic import field_validator

from app.schemas.common import ORMBase


def _valid_minimum_score(v: float | None) -> float | None:
    """Shared by MissionCreate/MissionUpdate — NULL means "completion is
    sufficient" (Stage 2's own documented semantics), never validated;
    a real value must fall inside the same 0-100 range every existing
    score field in this codebase already assumes (MissionAttempt.score,
    QuestAttempt.score, QuestEvaluationCriterion.max_score)."""
    if v is None:
        return v
    if not (0 <= v <= 100):
        raise ValueError("minimum_score must be between 0 and 100")
    return v


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
    minimum_score: float | None = None

    @field_validator("minimum_score")
    @classmethod
    def _check_minimum_score(cls, v: float | None) -> float | None:
        return _valid_minimum_score(v)


class MissionUpdate(ORMBase):
    title: str | None = None
    description: str | None = None
    mission_type: str | None = None
    estimated_minutes: int | None = None
    sort_order: int | None = None
    required: bool | None = None
    workspace_type: str | None = None
    minimum_score: float | None = None

    @field_validator("minimum_score")
    @classmethod
    def _check_minimum_score(cls, v: float | None) -> float | None:
        return _valid_minimum_score(v)


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
    minimum_score: float | None
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

from datetime import datetime

from pydantic import ValidationInfo, field_validator

from app.models.quest import QUEST_DIFFICULTIES, QUEST_STATUSES, QUEST_TYPES, WORKSPACE_TYPES
from app.schemas.common import ORMBase
from app.schemas.quest_capability import QuestCapabilityResponse
from app.schemas.quest_evaluation_criterion import QuestEvaluationCriterionInternal
from app.schemas.quest_evidence import QuestEvidenceResponse
from app.schemas.quest_task import QuestTaskResponse

_CHOICES: dict[str, list[str]] = {
    "quest_type": QUEST_TYPES,
    "workspace_type": WORKSPACE_TYPES,
    "difficulty": QUEST_DIFFICULTIES,
    "status": QUEST_STATUSES,
}


class QuestCreate(ORMBase):
    project_id: str | None = None
    department_id: str | None = None
    created_by_employee_id: str | None = None
    title: str
    description: str | None = None
    quest_type: str
    workspace_type: str
    difficulty: str = "MEDIUM"
    status: str = "DRAFT"

    @field_validator("quest_type", "workspace_type", "difficulty", "status")
    @classmethod
    def _valid_choice(cls, v: str, info: ValidationInfo) -> str:
        allowed = _CHOICES[info.field_name]
        if v not in allowed:
            raise ValueError(f"{info.field_name} must be one of {allowed}")
        return v


class QuestUpdate(ORMBase):
    """No `status` field — Stage 3 requires publishing/archiving to go
    through their own dedicated endpoints (POST .../publish,
    .../archive), each with its own lifecycle and eligibility validation,
    rather than being silently mutable through an ordinary PATCH. A
    `status` key in the request body is simply ignored (ORMBase doesn't
    set extra="forbid"), not rejected — there is nothing left in this
    model that could act on it."""

    project_id: str | None = None
    department_id: str | None = None
    created_by_employee_id: str | None = None
    title: str | None = None
    description: str | None = None
    quest_type: str | None = None
    workspace_type: str | None = None
    difficulty: str | None = None

    @field_validator("quest_type", "workspace_type", "difficulty")
    @classmethod
    def _valid_choice(cls, v: str | None, info: ValidationInfo) -> str | None:
        if v is None:
            return v
        allowed = _CHOICES[info.field_name]
        if v not in allowed:
            raise ValueError(f"{info.field_name} must be one of {allowed}")
        return v


class QuestResponse(ORMBase):
    id: str
    project_id: str | None
    department_id: str | None
    created_by_employee_id: str | None
    title: str
    description: str | None
    quest_type: str
    workspace_type: str
    difficulty: str
    status: str
    created_at: datetime
    updated_at: datetime

    @field_validator("quest_type", "workspace_type", "difficulty", "status")
    @classmethod
    def _valid_choice(cls, v: str, info: ValidationInfo) -> str:
        allowed = _CHOICES[info.field_name]
        if v not in allowed:
            raise ValueError(f"{info.field_name} must be one of {allowed}")
        return v


class QuestDetailResponse(ORMBase):
    """Manager/server-side representation — includes everything, including
    QuestEvaluationCriterionInternal's hidden expected_answer/
    expected_behavior/reference_solution. Never return this from an
    employee-facing endpoint; use EmployeeQuestResponse below instead."""

    id: str
    project_id: str | None
    department_id: str | None
    created_by_employee_id: str | None
    title: str
    description: str | None
    quest_type: str
    workspace_type: str
    difficulty: str
    status: str
    created_at: datetime
    updated_at: datetime

    tasks: list[QuestTaskResponse]
    evidence: list[QuestEvidenceResponse]
    evaluation_criteria: list[QuestEvaluationCriterionInternal]
    capabilities: list[QuestCapabilityResponse]

    @field_validator("quest_type", "workspace_type", "difficulty", "status")
    @classmethod
    def _valid_choice(cls, v: str, info: ValidationInfo) -> str:
        allowed = _CHOICES[info.field_name]
        if v not in allowed:
            raise ValueError(f"{info.field_name} must be one of {allowed}")
        return v


class EmployeeQuestResponse(ORMBase):
    """The safe contract for a future employee-facing Quest Workspace
    (Stage 4). Structurally incapable of leaking evaluation data — there
    is no field here that could hold a QuestEvaluationCriterionInternal,
    unlike QuestDetailResponse above. Not wired to any route yet; Stage 2
    only establishes the contract (see Phase 3B Stage 2 spec §17).

    `required_for_readiness` (Phase 8H-3) — independent of Quest
    completion and independent of whether this Quest happens to be the
    current recommendation (see readiness_service.required_eligible_
    quest_ids and quest_recommendation.py, which never reference one
    another). Its `False` default here exists ONLY to satisfy Pydantic's
    ORM-passthrough validation (the underlying Quest ORM object has no
    such attribute at all) — every endpoint that returns this schema
    MUST overlay the real, computed value via `.model_copy(update=...)`
    immediately after `model_validate`; the bare default must never
    reach a client. See api/v1/endpoints/quests.py's get_employee_quest
    and capabilities.py's get_next_quest, the only two places this
    schema is ever constructed."""

    id: str
    title: str
    description: str | None
    quest_type: str
    workspace_type: str
    difficulty: str
    tasks: list[QuestTaskResponse]
    evidence: list[QuestEvidenceResponse]
    required_for_readiness: bool = False

    @field_validator("quest_type", "workspace_type", "difficulty")
    @classmethod
    def _valid_choice(cls, v: str, info: ValidationInfo) -> str:
        allowed = _CHOICES[info.field_name]
        if v not in allowed:
            raise ValueError(f"{info.field_name} must be one of {allowed}")
        return v


class QuestQualityCheck(ORMBase):
    """Phase 6B — one Quest Quality Validation check. `section` matches a
    Manager Quest Builder tab key 1:1 (basic-info/challenge/work-evidence/
    evaluation/capabilities/assign-publish) so the frontend can deep-link
    a manager straight to the section that needs attention."""

    code: str
    severity: str
    message: str
    section: str
    satisfied: bool


class QuestQualityValidationResponse(ORMBase):
    ready: bool
    errors: list[QuestQualityCheck]
    warnings: list[QuestQualityCheck]
    checks: list[QuestQualityCheck]

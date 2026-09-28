from datetime import datetime

from pydantic import field_validator

from app.models.quest_attempt import QUEST_ATTEMPT_STATUSES
from app.schemas.common import JSONValue, ORMBase


class QuestAttemptCreate(ORMBase):
    quest_id: str
    employee_id: str


class QuestAttemptUpdate(ORMBase):
    """Autosave payload. `employee_id` is required so the endpoint can
    verify ownership before writing anything — this project has no
    session-based auth yet, so it follows the same established
    employee_id-in-body pattern as MissionAttemptSubmit.

    `completed_task_ids`, when provided, REPLACES the stored list
    wholesale rather than merging — the frontend always holds the
    complete current checkbox state (unlike MissionAttempt's
    evidence_viewed, which accumulates incrementally as evidence panels
    are opened one at a time).

    `workspace` (Phase 7 Stage 1) is the additive envelope for a
    specialized Workspace's own payload — `{"type": ..., "payload": ...}`
    — added alongside findings/reasoning/solution/completed_task_ids
    rather than replacing them, so every existing reader of this shape
    (evaluate_deterministic, QuestAIEvaluationContext, capability
    evidence) keeps working unmodified whether or not a given attempt
    ever sets it."""

    employee_id: str
    findings: str | None = None
    reasoning: str | None = None
    solution: str | None = None
    completed_task_ids: list[str] | None = None
    workspace: dict[str, JSONValue] | None = None


class QuestAttemptSubmit(ORMBase):
    employee_id: str


class QuestAttemptResponse(ORMBase):
    id: str
    quest_id: str
    employee_id: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    submission: dict[str, JSONValue]
    score: float | None
    passed: bool | None
    feedback: str | None
    created_at: datetime
    updated_at: datetime

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        if v not in QUEST_ATTEMPT_STATUSES:
            raise ValueError(f"status must be one of {QUEST_ATTEMPT_STATUSES}")
        return v

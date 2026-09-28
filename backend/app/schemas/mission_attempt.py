from datetime import datetime

from app.schemas.common import ORMBase


class EvidenceItem(ORMBase):
    id: str
    label: str
    detail: str


class TimelineItem(ORMBase):
    id: str
    time: str
    label: str


class MissionScenarioRead(ORMBase):
    mission_id: str
    briefing: str
    metrics: list[EvidenceItem]
    logs: list[EvidenceItem]
    services: list[EvidenceItem]
    timeline: list[TimelineItem]
    service_options: list[str]
    cause_options: list[str]


class MissionQuizQuestionRead(ORMBase):
    id: str
    prompt: str
    options: list[str]


class MissionQuizRead(ORMBase):
    mission_id: str
    briefing: str
    questions: list[MissionQuizQuestionRead]


class MissionAttemptCreate(ORMBase):
    mission_id: str
    employee_id: str


class MissionAttemptUpdate(ORMBase):
    affected_service: str | None = None
    likely_cause: str | None = None
    reasoning: str | None = None
    evidence_viewed: list[str] | None = None
    quiz_answers: dict[str, str] | None = None


class MissionAttemptSubmit(ORMBase):
    """Fields are optional at the schema level because which ones are
    required depends on the Mission's `workspace_type` — enforced in
    mission_attempt_service.submit_attempt, not here, since that's where
    the Mission (and therefore its workspace_type) is actually known."""

    employee_id: str
    affected_service: str | None = None
    likely_cause: str | None = None
    reasoning: str | None = None
    evidence_viewed: list[str] = []
    quiz_answers: dict[str, str] | None = None


class MissionAttemptRead(ORMBase):
    id: str
    mission_id: str
    employee_id: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    affected_service: str | None
    likely_cause: str | None
    reasoning: str | None
    evidence_viewed: list[str]
    quiz_answers: dict[str, str]
    score: float | None
    passed: bool | None
    feedback: str | None

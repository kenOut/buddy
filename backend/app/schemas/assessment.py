from datetime import datetime
from typing import Any

from app.schemas.common import ORMBase


class AssessmentAnswer(ORMBase):
    question_id: str
    selected_option: str


class AssessmentSubmit(ORMBase):
    onboarding_session_id: str
    employee_id: str
    answers: list[AssessmentAnswer]


class AssessmentRead(ORMBase):
    id: str
    onboarding_session_id: str
    employee_id: str
    score: float | None
    passed: bool | None
    answers: dict[str, Any]
    submitted_at: datetime | None
    created_at: datetime

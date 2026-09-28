from datetime import datetime

from app.schemas.ai_evaluation import AIEvaluationResponse
from app.schemas.common import ORMBase


class CapabilityEvaluationRead(ORMBase):
    """The audit record. `structured_result` is the validated
    AIEvaluationResponse as stored — typed here so API consumers get the
    same shape guarantees as the AI provider boundary itself, never a
    loose `dict[str, Any]`."""

    id: str
    mission_attempt_id: str | None
    quest_attempt_id: str | None
    employee_id: str

    model: str
    prompt_version: str
    evaluation_version: str

    structured_result: AIEvaluationResponse

    created_at: datetime


class EvaluateMissionAttemptRequest(ORMBase):
    employee_id: str

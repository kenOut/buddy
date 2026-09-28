from datetime import datetime

from app.schemas.ai_evaluation import AICapabilityAssessment
from app.schemas.common import ORMBase


class EvaluateQuestAttemptRequest(ORMBase):
    employee_id: str


class QuestEvaluationEmployeeResponse(ORMBase):
    """The employee-safe evaluation contract — a purpose-built shape, not
    a reuse of CapabilityEvaluationRead's raw metadata (model/
    prompt_version/evaluation_version aren't meaningful to an employee).
    Built from the same validated AIEvaluationResponse
    (structured_result) that already excludes raw_response and anything
    resembling a hidden answer key — there is no field here, and no way
    to add one accidentally, that could carry expected_answer/
    expected_behavior/reference_solution."""

    status: str
    summary: str
    strengths: list[str]
    development_areas: list[str]
    capabilities: list[AICapabilityAssessment]
    recommended_focus: str
    evaluated_at: datetime

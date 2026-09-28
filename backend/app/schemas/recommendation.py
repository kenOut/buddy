from datetime import datetime

from app.schemas.mission import MissionRead
from app.schemas.common import ORMBase
from app.schemas.quest import EmployeeQuestResponse


class NextMissionResponse(ORMBase):
    mission: MissionRead | None
    reason: str
    target_capabilities: list[str]


class CapabilityGapItemResponse(ORMBase):
    """Phase 6C — one capability's classification in a gap analysis.
    `category` is one of STRENGTH/CAPABLE/DEVELOPMENT_AREA/UNOBSERVED —
    deliberately never a numeric score."""

    capability: str
    capability_name: str
    current_level: str
    category: str
    reason: str


class CapabilityGapAnalysisResponse(ORMBase):
    employee_id: str
    strengths: list[CapabilityGapItemResponse]
    development_areas: list[CapabilityGapItemResponse]
    unobserved: list[CapabilityGapItemResponse]
    assessed_capabilities: list[CapabilityGapItemResponse]
    generated_at: datetime


class NextQuestResponse(ORMBase):
    """Employee-safe by construction: `recommended_quest` is typed as
    EmployeeQuestResponse, the same structurally-safe schema the Quest
    Workspace itself uses — there is no field here, or on that type,
    capable of carrying expected_answer/expected_behavior/
    reference_solution/evaluation criteria internals."""

    recommended_quest: EmployeeQuestResponse | None
    reason: str
    target_capabilities: list[str]
    gap_analysis: CapabilityGapAnalysisResponse | None = None

"""Phase 6E — Manager Analytics response schemas.

Every metric here is a literal count or a plainly-defined ratio computed
from existing authoritative records (Quest, QuestAttempt, QuestAssignment,
CapabilityEvidence, CapabilityProfile, Recommendation). Nothing is scored,
ranked, or judged — see services/analytics_service.py for exact
definitions of each field. No field on any of these models is capable of
carrying expected_answer/expected_behavior/reference_solution/raw AI
responses/evaluator configuration; those types (QuestEvaluationCriterion,
CapabilityEvaluation.raw_response/model/prompt_version) are never read by
analytics_service.py at all.
"""

from datetime import datetime

from app.schemas.common import ORMBase


class RecentRecommendationItem(ORMBase):
    recommendation_id: str
    employee_id: str
    employee_name: str
    quest_id: str
    quest_title: str
    reason: str
    target_capabilities: list[str]
    created_at: datetime


class AnalyticsOverviewResponse(ORMBase):
    department_id: str | None

    # Quest activity
    published_quests: int
    draft_quests: int
    archived_quests: int
    active_assignment_records: int
    employees_reached: int

    attempts_total: int
    attempts_not_started: int
    attempts_in_progress: int
    attempts_submitted: int
    attempts_evaluating: int
    attempts_completed: int

    # Development activity (both Mission- and Quest-sourced evidence)
    employees_with_capability_evidence: int
    capability_observations: int
    recommendations_generated: int
    employees_with_development_history: int
    recent_recommendations: list[RecentRecommendationItem]


class QuestAnalyticsSummary(ORMBase):
    quest_id: str
    title: str
    quest_type: str
    status: str
    difficulty: str
    project_id: str | None
    project_name: str | None
    capability_count: int
    assigned_employees: int
    attempts_total: int
    attempts_completed: int
    completion_rate: float | None
    evidence_count: int
    recommendation_count: int
    signals: list[str]


class QuestAnalyticsResponse(ORMBase):
    department_id: str | None
    quests: list[QuestAnalyticsSummary]


class QuestCapabilityEvidenceBreakdown(ORMBase):
    capability_key: str
    capability_name: str
    evidence_count: int


class QuestDetailAnalyticsResponse(ORMBase):
    quest_id: str
    title: str
    quest_type: str
    status: str
    difficulty: str
    project_id: str | None
    project_name: str | None

    assigned_employees: int
    attempts_total: int
    attempts_not_started: int
    attempts_in_progress: int
    attempts_submitted: int
    attempts_evaluating: int
    attempts_completed: int
    completion_rate: float | None

    evidence_count: int
    capability_breakdown: list[QuestCapabilityEvidenceBreakdown]
    evaluation_criteria_count: int

    recommendation_count: int
    signals: list[str]


class CapabilityLevelBreakdown(ORMBase):
    level: str
    employee_count: int


class QuestEvidenceSource(ORMBase):
    quest_id: str
    quest_title: str
    evidence_count: int


class CapabilityAnalyticsSummary(ORMBase):
    capability_id: str
    capability_key: str
    capability_name: str
    total_employees: int
    observed_employees: int
    not_observed_employees: int
    level_breakdown: list[CapabilityLevelBreakdown]
    development_area_employees: int
    quests_producing_evidence: list[QuestEvidenceSource]


class CapabilityAnalyticsResponse(ORMBase):
    department_id: str | None
    capabilities: list[CapabilityAnalyticsSummary]


class DevelopmentSignalItem(ORMBase):
    capability_id: str
    capability_key: str
    capability_name: str
    employee_count: int


class DevelopmentSignalsResponse(ORMBase):
    department_id: str | None
    development_areas: list[DevelopmentSignalItem]


class CapabilityEmployeeItem(ORMBase):
    employee_id: str
    full_name: str
    department_name: str | None
    role_title: str | None
    level: str
    evidence_count: int


class CapabilityEmployeesResponse(ORMBase):
    capability_id: str
    capability_key: str
    capability_name: str
    category: str
    department_id: str | None
    employees: list[CapabilityEmployeeItem]


class EmployeeCapabilitySummary(ORMBase):
    capability_key: str
    capability_name: str
    level: str
    category: str
    evidence_count: int


class EmployeeQuestActivityItem(ORMBase):
    quest_id: str
    quest_title: str
    status: str
    completed_at: datetime | None


class EmployeeRecommendationSummary(ORMBase):
    quest_id: str
    quest_title: str
    reason: str
    target_capabilities: list[str]
    created_at: datetime


class EmployeeAnalyticsResponse(ORMBase):
    employee_id: str
    full_name: str
    department_id: str | None
    department_name: str | None
    role_title: str | None
    capabilities: list[EmployeeCapabilitySummary]
    development_areas: list[str]
    recent_quest_activity: list[EmployeeQuestActivityItem]
    latest_recommendation: EmployeeRecommendationSummary | None

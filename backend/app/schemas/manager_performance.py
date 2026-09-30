"""Manager Performance & Readiness Visibility — Stage 1.

The manager-safe read model for "how is this employee actually
performing," assembled entirely from data the system already computes
and persists (Mission/QuestAttempt scores, CapabilityProfile levels,
readiness_service's existing predicate) — nothing here introduces a new
scoring rule, a new readiness rule, or a new evaluation concept. See
manager_performance_service.py for how each section is assembled and
which existing service each one reuses rather than re-derives.

Structurally employee-safe by the same pattern EmployeeQuestResponse/
QuestEvaluationEmployeeResponse already establish: no field here is
capable of holding expected_answer/expected_behavior/reference_solution,
a scenario's correct_service/correct_cause, a quiz's correct_option, or
any raw AI provider output — those types are never read by
manager_performance_service.py at all. This is a manager-facing view of
RESULTS, not of the answer keys that produced them.
"""

from datetime import datetime

from app.schemas.common import ORMBase


class ManagerEmployeeInfo(ORMBase):
    id: str
    full_name: str
    email: str
    job_title: str | None
    department_id: str | None
    department_name: str | None
    team: str | None


class ManagerReadinessInfo(ORMBase):
    """Exposes readiness_service.get_readiness_summary's existing fields
    verbatim (ready/onboarding_completed/the six required-and-completed
    counts) plus `blockers` — plain-language strings derived from the
    same required-vs-completed id sets readiness_service already
    computes and exposes publicly (required_eligible_quest_ids/
    required_eligible_mission_ids), never a new eligibility or
    completion rule invented for this endpoint."""

    ready: bool
    onboarding_completed: bool

    required_quest_count: int
    completed_required_quest_count: int
    remaining_required_quest_count: int

    required_mission_count: int
    completed_required_mission_count: int
    remaining_required_mission_count: int

    blockers: list[str]


class ManagerMissionPerformance(ORMBase):
    id: str
    title: str
    required: bool
    # MissionAssignment.status (pending/in_progress/completed) — the
    # lifecycle status Missions have always tracked.
    assignment_status: str
    # MissionAttempt.status (not_started/in_progress/submitted/completed),
    # or None when no attempt has ever been started — a strictly more
    # granular signal than assignment_status alone (e.g. a failed,
    # retryable attempt sits at "submitted" while the assignment itself
    # is still "in_progress").
    attempt_status: str | None
    score: float | None
    passed: bool | None
    feedback: str | None
    completed_at: datetime | None


class ManagerQuestPerformance(ORMBase):
    id: str
    title: str
    required: bool
    # QuestAssignment carries no lifecycle status field of its own (only
    # active/required booleans) — unlike Mission, a Quest's progress is
    # already fully expressed by its QuestAttempt status alone, so there
    # is no separate "assignment_status" to report here; None means no
    # attempt has been started yet.
    attempt_status: str | None
    score: float | None
    passed: bool | None
    feedback: str | None
    completed_at: datetime | None


class ManagerCapabilitySummary(ORMBase):
    capability_id: str
    capability_key: str
    capability_name: str
    level: str
    confidence: float
    evidence_count: int


class ManagerPerformanceSummary(ORMBase):
    """Informational only — `average_score` must never be read as a
    readiness signal (readiness_service never sees this value, and
    nothing here computes or triggers readiness). Genuinely unscored
    (score IS NULL) rows are excluded from both `scored_items` and the
    average, never coerced to 0 — an attempt nobody has evaluated is not
    the same fact as one that scored zero."""

    missions_assigned: int
    missions_completed: int
    quests_assigned: int
    quests_completed: int
    scored_items: int
    average_score: float | None


class ManagerEmployeePerformanceResponse(ORMBase):
    employee: ManagerEmployeeInfo
    readiness: ManagerReadinessInfo
    missions: list[ManagerMissionPerformance]
    quests: list[ManagerQuestPerformance]
    capabilities: list[ManagerCapabilitySummary]
    performance_summary: ManagerPerformanceSummary

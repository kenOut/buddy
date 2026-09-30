"""Manager Performance & Readiness Visibility — Stage 1, extended by
Stage 2 (Performance-Aware Readiness).

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

Stage 2 adds `minimum_score`/`threshold_status` per Mission/Quest row
and upgrades `blockers` from plain strings to readiness_service's own
structured `ReadinessBlocker` type — both sourced from
readiness_service.required_quest_items/required_mission_items/
get_readiness_blockers, never re-derived here (Stage 2 §8).
"""

from datetime import datetime

from app.schemas.common import ORMBase
from app.schemas.readiness import ReadinessBlocker


class ManagerEmployeeInfo(ORMBase):
    id: str
    full_name: str
    email: str
    job_title: str | None
    department_id: str | None
    department_name: str | None
    team: str | None


class ManagerReadinessInfo(ORMBase):
    """Exposes readiness_service.get_readiness_summary's fields verbatim
    (ready/onboarding_completed/the six required-and-completed counts,
    plus Stage 2's `required_items_below_threshold`) alongside
    `blockers` — readiness_service.get_readiness_blockers' own
    structured output, never a second, independently-derived notion of
    "why not ready" computed here."""

    ready: bool
    onboarding_completed: bool

    required_quest_count: int
    completed_required_quest_count: int
    remaining_required_quest_count: int

    required_mission_count: int
    completed_required_mission_count: int
    remaining_required_mission_count: int

    required_items_below_threshold: int

    blockers: list[ReadinessBlocker]


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
    # Stage 2 — Mission.minimum_score, and the same SATISFIED/
    # BELOW_THRESHOLD/INCOMPLETE classification readiness_service's own
    # RequiredItemState.satisfied uses. Both None when this Mission
    # isn't required at all — a threshold is only ever meaningful on a
    # required item.
    minimum_score: float | None
    threshold_status: str | None


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
    # Stage 2 — QuestAssignment.minimum_score (the strictest configured
    # value, if the employee matches more than one required assignment
    # on this Quest — see readiness_service.required_quest_items) and
    # its SATISFIED/BELOW_THRESHOLD/INCOMPLETE classification. Both None
    # when this Quest isn't required for this employee.
    minimum_score: float | None
    threshold_status: str | None


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
    the same fact as one that scored zero. Unchanged by Stage 2: this
    remains a plain average of whatever happens to be scored, never
    consulted by readiness_service's per-item threshold predicate."""

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

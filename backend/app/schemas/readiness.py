from pydantic import field_validator

from app.schemas.common import ORMBase

# Stage 2 — Performance-Aware Readiness. ONBOARDING_INCOMPLETE has no
# underlying Mission/Quest, so its item_id is None; every other type
# names the specific item that's blocking. The *_INCOMPLETE vs
# *_BELOW_THRESHOLD split mirrors the two distinct ways a required item
# can fail to satisfy readiness — see readiness_service.py's
# RequiredItemState.satisfied for the actual predicate this classifies.
READINESS_BLOCKER_TYPES = [
    "ONBOARDING_INCOMPLETE",
    "REQUIRED_MISSION_INCOMPLETE",
    "REQUIRED_MISSION_BELOW_THRESHOLD",
    "REQUIRED_QUEST_INCOMPLETE",
    "REQUIRED_QUEST_BELOW_THRESHOLD",
]


class ReadinessBlocker(ORMBase):
    """Manager-safe, structured readiness explanation — built by
    readiness_service.get_readiness_blockers from the exact same
    required-item state is_ready() itself evaluates, never a second,
    independently-derived notion of "why not ready". `score`/
    `minimum_score` are real numeric values, so this type is deliberately
    NEVER returned from an employee-facing endpoint (see
    EmployeeReadinessSummary below, which stays aggregate-only) — Quest
    scores specifically are never shown to the employee anywhere in this
    system (see QuestEvaluationEmployeeResponse's own docstring), and
    this type would leak exactly that if exposed to them. Structurally
    incapable of carrying evaluation criteria, expected answers, or any
    other evaluator-only content — there is no field here that could
    hold it.
    """

    type: str
    item_id: str | None
    title: str
    score: float | None
    minimum_score: float | None

    @field_validator("type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        if v not in READINESS_BLOCKER_TYPES:
            raise ValueError(f"type must be one of {READINESS_BLOCKER_TYPES}")
        return v


class EmployeeReadinessSummary(ORMBase):
    """Phase 8H-1 — the employee-safe view of readiness_service's
    predicate (extended to Missions alongside Quests — see that
    module's docstring). Deliberately minimal: counts only, never a
    Quest/Mission id/title/assignment detail, never anything about
    *why* a specific Quest or Mission is or isn't in the required set
    (that's internal to readiness_service.py's eligibility resolution).
    Nothing here can carry evaluation criteria, expected answers, AI
    evaluation material, or another employee's data — this type
    structurally has no field capable of holding any of it.

    Stage 2 adds exactly one field, `required_items_below_threshold` —
    an aggregate count, deliberately not a list of which items or their
    scores (see ReadinessBlocker above for why: Quest scores are never
    shown to the employee anywhere else in this system, and this
    summary must not become the one place that does). Every field that
    existed before Stage 2 keeps its exact pre-Stage-2 meaning:
    `completed_required_quest_count`/`completed_required_mission_count`
    still count *completion*, not *performance* — a required item that
    was completed but scored below its threshold still counts as
    completed here (and also counts in `required_items_below_threshold`
    below); only `ready` itself reflects the stricter, threshold-aware
    predicate.
    """

    ready: bool
    onboarding_completed: bool
    required_quest_count: int
    completed_required_quest_count: int
    remaining_required_quest_count: int
    required_mission_count: int
    completed_required_mission_count: int
    remaining_required_mission_count: int
    required_items_below_threshold: int

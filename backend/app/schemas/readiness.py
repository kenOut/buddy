from app.schemas.common import ORMBase


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
    """

    ready: bool
    onboarding_completed: bool
    required_quest_count: int
    completed_required_quest_count: int
    remaining_required_quest_count: int
    required_mission_count: int
    completed_required_mission_count: int
    remaining_required_mission_count: int

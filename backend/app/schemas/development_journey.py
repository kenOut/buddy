from datetime import datetime

from app.schemas.common import ORMBase


class DevelopmentJourneyItem(ORMBase):
    """Phase 6D — one entry in an employee's development timeline.
    Structurally incapable of carrying evaluator-only content: there is
    no field here that could hold expected_answer/expected_behavior/
    reference_solution, a raw AI response, or scoring configuration —
    every value is either a title/description string built from
    already-employee-safe sources (Quest.title, Capability.name, a
    persisted Recommendation.reason) or a plain identifier/timestamp."""

    id: str
    type: str
    timestamp: datetime
    title: str
    description: str
    quest_id: str | None = None
    quest_available: bool | None = None
    capability: str | None = None
    level: str | None = None
    reason: str | None = None
    target_capabilities: list[str] | None = None
    # Phase 8H-2 — WORKSPACE_ACCESS_GRANTED only. Mirrors EmployeeWork
    # spaceAccess's own safe-field discipline exactly: a workspace's
    # display name and employee-facing link are fine here; nothing
    # resembling external_ref/provider/provider_ref/last_error/
    # attempt_count is a field on this type, so there is nothing for
    # those to leak through even by accident.
    workspace_name: str | None = None
    workspace_link: str | None = None


class DevelopmentJourneyResponse(ORMBase):
    employee_id: str
    items: list[DevelopmentJourneyItem]

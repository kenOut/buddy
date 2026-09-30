from datetime import datetime

from pydantic import field_validator, model_validator

from app.models.quest_assignment import ASSIGNMENT_TYPES
from app.schemas.common import ORMBase

_TARGET_FIELD = {
    "EMPLOYEE": "employee_id",
    "DEPARTMENT": "department_id",
    "ROLE": "role_id",
}


def _valid_minimum_score(v: float | None) -> float | None:
    """Shared by QuestAssignmentCreate/Update — NULL means "completion is
    sufficient" (Stage 2's own documented semantics), never validated; a
    real value must fall inside the same 0-100 range every existing
    score field in this codebase already assumes (QuestAttempt.score,
    MissionAttempt.score, QuestEvaluationCriterion.max_score)."""
    if v is None:
        return v
    if not (0 <= v <= 100):
        raise ValueError("minimum_score must be between 0 and 100")
    return v


class QuestAssignmentCreate(ORMBase):
    assignment_type: str
    employee_id: str | None = None
    department_id: str | None = None
    role_id: str | None = None
    # Phase 8H-3 (launch-audit follow-up): exposes the existing
    # QuestAssignment.required column through the manager-facing API —
    # the column, readiness_service's read of it, and required_for_
    # readiness were all already live; only the write path was missing.
    # Defaults False so an assignment created without specifying this
    # stays optional, matching the column's own DB-level default.
    required: bool = False
    # Stage 2 — Performance-Aware Readiness. See QuestAssignment.minimum_score's
    # own model docstring for why this lives on the assignment, not the Quest.
    minimum_score: float | None = None

    @field_validator("assignment_type")
    @classmethod
    def _valid_assignment_type(cls, v: str) -> str:
        if v not in ASSIGNMENT_TYPES:
            raise ValueError(f"assignment_type must be one of {ASSIGNMENT_TYPES}")
        return v

    @field_validator("minimum_score")
    @classmethod
    def _check_minimum_score(cls, v: float | None) -> float | None:
        return _valid_minimum_score(v)

    @model_validator(mode="after")
    def _exactly_one_matching_target(self) -> "QuestAssignmentCreate":
        populated = [
            field
            for field in ("employee_id", "department_id", "role_id")
            if getattr(self, field) is not None
        ]
        if len(populated) != 1:
            raise ValueError(
                "Exactly one of employee_id/department_id/role_id must be set "
                f"(got: {populated or 'none'})"
            )
        expected_field = _TARGET_FIELD[self.assignment_type]
        if populated[0] != expected_field:
            raise ValueError(
                f"assignment_type={self.assignment_type!r} requires {expected_field} to be set, "
                f"not {populated[0]}"
            )
        return self


class QuestAssignmentUpdate(ORMBase):
    """Deliberately minimal: `active` and `required` are the only fields
    a manager can toggle post-creation. An assignment's target/type is
    treated as immutable once created — to reassign, delete and create a
    new one. This avoids re-deriving the single-target validation for
    every possible partial combination of (assignment_type, employee_id,
    department_id, role_id) changing independently.

    Setting `required` here only ever changes this one row — nothing
    else reads or writes as a side effect of this call. readiness_service
    picks the new value up the next time anything asks (it has never
    cached QuestAssignment.required and still doesn't); no
    QuestAttempt/CapabilityEvaluation/WorkspaceAccessGrant is touched,
    and no workspace grant is triggered from here — that only ever
    happens from readiness_service.check_and_trigger, called after a
    Quest/Mission completion commits, never from an assignment edit."""

    active: bool | None = None
    required: bool | None = None
    minimum_score: float | None = None

    @field_validator("minimum_score")
    @classmethod
    def _check_minimum_score(cls, v: float | None) -> float | None:
        return _valid_minimum_score(v)


class QuestAssignmentResponse(ORMBase):
    id: str
    quest_id: str
    assignment_type: str
    employee_id: str | None
    department_id: str | None
    role_id: str | None
    active: bool
    required: bool
    minimum_score: float | None
    created_at: datetime
    updated_at: datetime

    @field_validator("assignment_type")
    @classmethod
    def _valid_assignment_type(cls, v: str) -> str:
        if v not in ASSIGNMENT_TYPES:
            raise ValueError(f"assignment_type must be one of {ASSIGNMENT_TYPES}")
        return v


class QuestEligibilityResponse(ORMBase):
    """Access-eligibility only — never evaluation criteria, expected
    answers, or any other hidden Quest content."""

    eligible: bool
    quest_status: str
    matching_assignment_types: list[str]

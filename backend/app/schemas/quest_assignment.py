from datetime import datetime

from pydantic import field_validator, model_validator

from app.models.quest_assignment import ASSIGNMENT_TYPES
from app.schemas.common import ORMBase

_TARGET_FIELD = {
    "EMPLOYEE": "employee_id",
    "DEPARTMENT": "department_id",
    "ROLE": "role_id",
}


class QuestAssignmentCreate(ORMBase):
    assignment_type: str
    employee_id: str | None = None
    department_id: str | None = None
    role_id: str | None = None

    @field_validator("assignment_type")
    @classmethod
    def _valid_assignment_type(cls, v: str) -> str:
        if v not in ASSIGNMENT_TYPES:
            raise ValueError(f"assignment_type must be one of {ASSIGNMENT_TYPES}")
        return v

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
    """Deliberately minimal: only `active` can be toggled. An
    assignment's target/type is treated as immutable once created — to
    reassign, delete and create a new one. This avoids re-deriving the
    single-target validation for every possible partial combination of
    (assignment_type, employee_id, department_id, role_id) changing
    independently."""

    active: bool | None = None


class QuestAssignmentResponse(ORMBase):
    id: str
    quest_id: str
    assignment_type: str
    employee_id: str | None
    department_id: str | None
    role_id: str | None
    active: bool
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

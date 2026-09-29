"""Assignment CRUD plus the single authoritative eligibility check
(`is_employee_eligible`) — used by both the eligibility endpoint and
QuestAttempt creation, so there is exactly one place this logic lives
(see Phase 3B Stage 3 spec §10)."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, Quest, QuestAssignment
from app.schemas.quest_assignment import QuestAssignmentCreate, QuestAssignmentUpdate


class DuplicateQuestAssignmentError(Exception):
    """Raised when a Quest already has an assignment for the given
    target (same assignment_type + target). A genuine client error, not
    something to silently resolve like QuestAttempt's get-or-create."""


async def list_assignments(db: AsyncSession, quest_id: str) -> list[QuestAssignment]:
    stmt = (
        select(QuestAssignment)
        .where(QuestAssignment.quest_id == quest_id)
        .order_by(QuestAssignment.created_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_assignment(db: AsyncSession, quest_id: str, assignment_id: str) -> QuestAssignment | None:
    """Scoped to `quest_id` — never a bare `db.get(...)`, so an
    assignment belonging to a different quest can never be read,
    updated, or deleted through this quest's URL."""
    stmt = select(QuestAssignment).where(
        QuestAssignment.id == assignment_id, QuestAssignment.quest_id == quest_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_assignment(
    db: AsyncSession, quest_id: str, payload: QuestAssignmentCreate
) -> QuestAssignment:
    assignment = QuestAssignment(quest_id=quest_id, **payload.model_dump())
    db.add(assignment)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateQuestAssignmentError(
            f"Quest {quest_id} already has a {payload.assignment_type} assignment for this target"
        ) from exc
    await db.refresh(assignment)
    return assignment


async def update_assignment(
    db: AsyncSession, assignment: QuestAssignment, payload: QuestAssignmentUpdate
) -> QuestAssignment:
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(assignment, field, value)
    await db.commit()
    await db.refresh(assignment)
    return assignment


async def delete_assignment(db: AsyncSession, assignment: QuestAssignment) -> None:
    await db.delete(assignment)
    await db.commit()


async def has_active_assignment(db: AsyncSession, quest_id: str) -> bool:
    stmt = (
        select(QuestAssignment.id)
        .where(QuestAssignment.quest_id == quest_id, QuestAssignment.active.is_(True))
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


@dataclass
class EligibilityResult:
    eligible: bool
    matching_assignment_types: list[str]


def _assignment_matches_employee(assignment: QuestAssignment, employee: Employee) -> str | None:
    """The single predicate for "does this assignment cover this
    employee" — shared by get_matching_assignment_types (per-quest) and
    list_eligible_quest_ids_for_employee (Phase 8H-4, across every
    active assignment at once), so there is exactly one place this
    matching rule lives rather than two independently-maintained
    copies. Returns the matched assignment_type, or None."""
    if assignment.assignment_type == "EMPLOYEE" and assignment.employee_id == employee.id:
        return "EMPLOYEE"
    if (
        assignment.assignment_type == "DEPARTMENT"
        and employee.department_id is not None
        and assignment.department_id == employee.department_id
    ):
        return "DEPARTMENT"
    if (
        assignment.assignment_type == "ROLE"
        and employee.role_id is not None
        and assignment.role_id == employee.role_id
    ):
        return "ROLE"
    return None


async def get_matching_assignment_types(
    db: AsyncSession, quest_id: str, employee: Employee
) -> list[str]:
    """Resolved dynamically against QuestAssignment on every call — no
    materialized/synced eligibility table, per Stage 3 spec §12."""
    stmt = select(QuestAssignment).where(
        QuestAssignment.quest_id == quest_id, QuestAssignment.active.is_(True)
    )
    result = await db.execute(stmt)

    matched = {_assignment_matches_employee(a, employee) for a in result.scalars().all()}
    matched.discard(None)
    return sorted(matched)


async def is_employee_eligible(db: AsyncSession, quest: Quest, employee: Employee) -> EligibilityResult:
    if quest.status != "PUBLISHED":
        return EligibilityResult(eligible=False, matching_assignment_types=[])
    matched = await get_matching_assignment_types(db, quest.id, employee)
    return EligibilityResult(eligible=bool(matched), matching_assignment_types=matched)


async def list_eligible_quest_ids_for_employee(db: AsyncSession, employee: Employee) -> set[str]:
    """Phase 8H-4 — every PUBLISHED Quest this employee is eligible for
    (the employee's own Quest list, GET /employees/{id}/quests). Reuses
    the exact same per-assignment matching rule get_matching_assignment_
    types already applies one quest at a time (via
    _assignment_matches_employee) — not a second, independently-invented
    eligibility definition — just resolved across every active
    assignment joined to a PUBLISHED Quest in one query instead of
    looping is_employee_eligible over every Quest in existence."""
    stmt = (
        select(QuestAssignment)
        .join(Quest, Quest.id == QuestAssignment.quest_id)
        .where(QuestAssignment.active.is_(True), Quest.status == "PUBLISHED")
    )
    result = await db.execute(stmt)

    eligible: set[str] = set()
    for assignment in result.scalars().all():
        if _assignment_matches_employee(assignment, employee) is not None:
            eligible.add(assignment.quest_id)
    return eligible

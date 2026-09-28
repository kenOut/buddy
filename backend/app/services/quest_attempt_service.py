from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QuestAttempt
from app.schemas.quest_attempt import QuestAttemptUpdate
from app.services import quest_task_service

# The generic, quest-type-agnostic work fields (Stage 4 spec §13). At
# least one must be filled before submission — which one matters is left
# to the employee/quest type, not hard-coded per quest_type.
WORK_FIELDS = ("findings", "reasoning", "solution")


class QuestAttemptAlreadyFinalizedError(Exception):
    """Raised when a write (autosave or submit) is attempted against an
    attempt that's SUBMITTED, EVALUATING, or COMPLETED — a submitted
    quest must not silently become editable again (Stage 4 spec §6/§18),
    and that includes while evaluation is actively running (Stage 5)."""


class RequiredTasksIncompleteError(Exception):
    """Raised at submit time when one or more required QuestTasks haven't
    been marked complete. Never trust the frontend's task-completion
    flags — this is re-validated server-side against the quest's actual
    QuestTask rows."""

    def __init__(self, missing_task_ids: list[str]):
        self.missing_task_ids = missing_task_ids
        super().__init__(f"Required tasks not yet completed: {missing_task_ids}")


class IncompleteWorkSubmissionError(Exception):
    """Raised at submit time when none of findings/reasoning/solution has
    been recorded — an empty submission isn't meaningful regardless of
    quest type."""


async def get_attempt(db: AsyncSession, quest_id: str, employee_id: str) -> QuestAttempt | None:
    stmt = select(QuestAttempt).where(
        QuestAttempt.quest_id == quest_id,
        QuestAttempt.employee_id == employee_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_attempt_by_id(db: AsyncSession, attempt_id: str) -> QuestAttempt | None:
    return await db.get(QuestAttempt, attempt_id)


async def list_attempts_for_employee(db: AsyncSession, employee_id: str) -> list[QuestAttempt]:
    """Phase 6C: the recommendation engine needs this to exclude quests
    the employee has already completed. Bulk, not per-quest, so ranking
    a full candidate list doesn't issue one query per quest."""
    stmt = select(QuestAttempt).where(QuestAttempt.employee_id == employee_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_or_create_attempt(db: AsyncSession, quest_id: str, employee_id: str) -> QuestAttempt:
    """Upserts the single (quest, employee) row — mirrors
    mission_attempt_service.get_or_create_attempt exactly.

    The check-then-insert below isn't atomic, so two concurrent calls can
    both pass the "does it exist?" check before either commits. Rather
    than lock the table, the database's own unique constraint
    (uq_quest_attempt_quest_employee) is the tiebreaker: if we lose that
    race, we roll back and return the row the other request created
    instead of raising.
    """
    attempt = await get_attempt(db, quest_id, employee_id)
    if attempt:
        return attempt

    attempt = QuestAttempt(quest_id=quest_id, employee_id=employee_id, status="NOT_STARTED")
    db.add(attempt)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await get_attempt(db, quest_id, employee_id)
        if existing is not None:
            return existing
        raise
    await db.refresh(attempt)
    return attempt


async def update_submission(
    db: AsyncSession, attempt: QuestAttempt, payload: QuestAttemptUpdate
) -> QuestAttempt:
    """Autosave. Merges only the fields actually present in the request
    into the existing submission dict — an autosave call that only
    touches `reasoning` never clobbers a previously-saved `solution`."""
    if attempt.status in ("SUBMITTED", "EVALUATING", "COMPLETED"):
        raise QuestAttemptAlreadyFinalizedError("This quest attempt has already been submitted.")

    updates = payload.model_dump(exclude={"employee_id"}, exclude_unset=True, exclude_none=True)
    merged = dict(attempt.submission or {})
    merged.update(updates)
    attempt.submission = merged

    if attempt.status == "NOT_STARTED":
        attempt.status = "IN_PROGRESS"
        attempt.started_at = attempt.started_at or datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(attempt)
    return attempt


async def submit_attempt(db: AsyncSession, attempt: QuestAttempt, quest_id: str) -> QuestAttempt:
    """Deterministic, server-side submission validation — Stage 4 has no
    evaluation, so this only confirms the work is complete enough to
    hand off, never judges its quality."""
    if attempt.status in ("SUBMITTED", "EVALUATING", "COMPLETED"):
        raise QuestAttemptAlreadyFinalizedError("This quest attempt has already been submitted.")

    submission = attempt.submission or {}
    if not any(isinstance(submission.get(field), str) and submission[field].strip() for field in WORK_FIELDS):
        raise IncompleteWorkSubmissionError(
            "Record at least one of findings, reasoning, or solution before submitting."
        )

    tasks = await quest_task_service.list_tasks(db, quest_id)
    required_task_ids = [t.id for t in tasks if t.required]
    completed_ids = set(submission.get("completed_task_ids") or [])
    missing = [t for t in required_task_ids if t not in completed_ids]
    if missing:
        raise RequiredTasksIncompleteError(missing)

    attempt.status = "SUBMITTED"
    attempt.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(attempt)
    return attempt

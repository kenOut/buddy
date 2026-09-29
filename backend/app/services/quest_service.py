from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Quest, QuestCapability
from app.schemas.quest import QuestCreate, QuestUpdate
from app.services import quest_quality_service


class QuestLifecycleError(Exception):
    """Raised when a requested Quest status transition isn't allowed
    (e.g. publishing something that isn't DRAFT, or archiving something
    that isn't PUBLISHED)."""


class QuestNotPublishableError(Exception):
    """Raised when a DRAFT quest fails Quest Quality Validation (Phase
    6B) — one or more ERROR-severity checks are unsatisfied. See
    quest_quality_service.validate_quest for the full rule set."""


class QuestNotEditableError(Exception):
    """Raised when content mutation (basic info, tasks, evidence,
    evaluation criteria, capability mappings) is attempted against a
    non-DRAFT quest. Published Quest content must not change out from
    under employees who may already have attempts against that
    definition (Stage 6A §23) — there is no versioning system yet, so
    "read-only once published" is the safe default. QuestAssignment is
    deliberately NOT covered by this — who a quest is assigned to must
    stay changeable regardless of status."""


async def list_quests(db: AsyncSession, department_id: str | None = None) -> list[Quest]:
    stmt = select(Quest).order_by(Quest.created_at.desc())
    if department_id:
        stmt = stmt.where(Quest.department_id == department_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_quest(db: AsyncSession, quest_id: str) -> Quest | None:
    return await db.get(Quest, quest_id)


async def list_quests_by_ids(db: AsyncSession, quest_ids: set[str]) -> list[Quest]:
    """Phase 8H-4 — one bulk fetch for the employee Quest list (no
    content, unlike get_quest_with_content) instead of N individual
    db.get calls."""
    if not quest_ids:
        return []
    stmt = select(Quest).where(Quest.id.in_(quest_ids)).order_by(Quest.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_quest_with_content(db: AsyncSession, quest_id: str) -> Quest | None:
    """Eager-loads every child collection in one query set — used to build
    both QuestDetailResponse (manager/server, includes evaluation
    criteria) and EmployeeQuestResponse (safe subset) from the same
    fetch. Ordering within each collection comes from the relationship's
    own `order_by` (see models/quest.py), not from this query."""
    stmt = (
        select(Quest)
        .where(Quest.id == quest_id)
        .options(
            selectinload(Quest.tasks),
            selectinload(Quest.evidence),
            selectinload(Quest.evaluation_criteria),
            selectinload(Quest.capabilities).selectinload(QuestCapability.capability),
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_quest(db: AsyncSession, payload: QuestCreate) -> Quest:
    quest = Quest(**payload.model_dump())
    db.add(quest)
    await db.commit()
    await db.refresh(quest)
    return quest


def assert_quest_editable(quest: Quest) -> None:
    if quest.status != "DRAFT":
        raise QuestNotEditableError(
            f"This quest is {quest.status} and its content can no longer be edited. "
            "Archive it and create a new draft instead."
        )


async def update_quest(db: AsyncSession, quest: Quest, payload: QuestUpdate) -> Quest:
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(quest, field, value)
    await db.commit()
    await db.refresh(quest)
    return quest


async def publish_quest(db: AsyncSession, quest: Quest) -> Quest:
    """DRAFT -> PUBLISHED only, and only when Quest Quality Validation
    (Phase 6B, quest_quality_service.validate_quest) reports no
    ERROR-severity checks outstanding. Re-runs validation itself rather
    than trusting whatever the frontend last fetched from
    GET /quests/{id}/publish-readiness — that endpoint calls the same
    function, but this is the actual gate.

    The actual status flip is a conditional `UPDATE ... WHERE status =
    'DRAFT'` rather than a plain attribute set, so two concurrent publish
    requests for the same quest can't both succeed — same
    never-duplicate-under-concurrency philosophy as QuestAttempt's
    get-or-create elsewhere in this codebase, just expressed as an
    atomic conditional update instead of an IntegrityError-catch-and-
    refetch, since there's no unique constraint to violate here."""
    if quest.status != "DRAFT":
        raise QuestLifecycleError(
            f"Only a DRAFT quest can be published (current status: {quest.status})"
        )
    validation = await quest_quality_service.validate_quest(db, quest)
    if not validation.ready:
        failing = [c.message for c in validation.errors]
        raise QuestNotPublishableError(
            "Quest is not ready to publish: " + "; ".join(failing)
        )
    result = await db.execute(
        update(Quest).where(Quest.id == quest.id, Quest.status == "DRAFT").values(status="PUBLISHED")
    )
    await db.commit()
    if result.rowcount == 0:
        raise QuestLifecycleError(
            "Only a DRAFT quest can be published (status changed concurrently)"
        )
    await db.refresh(quest)
    return quest


async def archive_quest(db: AsyncSession, quest: Quest) -> Quest:
    """PUBLISHED -> ARCHIVED only. DRAFT -> ARCHIVED is deliberately not
    allowed: archiving means "this was live and is now retired," which a
    draft never was — see Stage 3 completion report for the full
    rationale."""
    if quest.status != "PUBLISHED":
        raise QuestLifecycleError(
            f"Only a PUBLISHED quest can be archived (current status: {quest.status})"
        )
    quest.status = "ARCHIVED"
    await db.commit()
    await db.refresh(quest)
    return quest

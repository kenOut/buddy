"""Phase 6D — plain read/write for the Recommendation domain. Append-only
by construction: this module has no update or delete function, matching
the "no UPDATE endpoint, no DELETE endpoint" requirement — there is
nothing here for an endpoint to call even if one were added by mistake.

Decision logic for *when* to create vs. reuse a row lives in
recommendation_persistence.py, not here — this module only knows how to
read and insert.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Recommendation


async def get_latest_for_employee(
    db: AsyncSession, employee_id: str, recommendation_type: str
) -> Recommendation | None:
    """The single most recent recommendation of this type for this
    employee — the "active" recommendation that a fresh GET compares
    against to decide reuse-vs-create (Phase 6D Part 6)."""
    stmt = (
        select(Recommendation)
        .where(
            Recommendation.employee_id == employee_id,
            Recommendation.recommendation_type == recommendation_type,
        )
        .order_by(Recommendation.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_for_employee(db: AsyncSession, employee_id: str) -> list[Recommendation]:
    """All recommendation history for this employee, oldest first — the
    Development Journey's recommendation source (Part 8D)."""
    stmt = (
        select(Recommendation)
        .where(Recommendation.employee_id == employee_id)
        .order_by(Recommendation.created_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_recommendation(
    db: AsyncSession,
    *,
    employee_id: str,
    quest_id: str,
    recommendation_type: str,
    reason: str,
    target_capabilities: list[str],
    capability_snapshot: dict,
    context_hash: str,
) -> Recommendation:
    recommendation = Recommendation(
        employee_id=employee_id,
        quest_id=quest_id,
        recommendation_type=recommendation_type,
        reason=reason,
        target_capabilities=target_capabilities,
        capability_snapshot=capability_snapshot,
        context_hash=context_hash,
    )
    db.add(recommendation)
    await db.commit()
    await db.refresh(recommendation)
    return recommendation

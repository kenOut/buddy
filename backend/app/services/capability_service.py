"""CRUD/retrieval for the capability domain. Aggregation math (how evidence
turns into a profile's level/score/confidence) lives in
capability_aggregation.py — this module only reads and writes rows.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Capability, CapabilityEvidence, CapabilityProfile


async def list_capabilities(db: AsyncSession) -> list[Capability]:
    result = await db.execute(select(Capability).order_by(Capability.name))
    return list(result.scalars().all())


async def get_capability(db: AsyncSession, capability_id: str) -> Capability | None:
    return await db.get(Capability, capability_id)


async def get_capability_by_key(db: AsyncSession, key: str) -> Capability | None:
    result = await db.execute(select(Capability).where(Capability.key == key))
    return result.scalar_one_or_none()


async def list_profiles_for_employee(db: AsyncSession, employee_id: str) -> list[CapabilityProfile]:
    stmt = (
        select(CapabilityProfile)
        .where(CapabilityProfile.employee_id == employee_id)
        .options(selectinload(CapabilityProfile.capability))
        .join(Capability, CapabilityProfile.capability_id == Capability.id)
        .order_by(Capability.name)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_profile(
    db: AsyncSession, employee_id: str, capability_id: str
) -> CapabilityProfile | None:
    stmt = (
        select(CapabilityProfile)
        .where(
            CapabilityProfile.employee_id == employee_id,
            CapabilityProfile.capability_id == capability_id,
        )
        .options(selectinload(CapabilityProfile.capability))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_profile(
    db: AsyncSession,
    employee_id: str,
    capability_id: str,
    *,
    level: str,
    score: float,
    confidence: float,
    evidence_count: int,
) -> CapabilityProfile:
    """The write side of aggregation — always recomputed from evidence,
    never incremented/patched in place, so it can never drift from what
    the evidence actually supports."""
    profile = await get_profile(db, employee_id, capability_id)
    if profile is None:
        profile = CapabilityProfile(employee_id=employee_id, capability_id=capability_id)
        db.add(profile)

    profile.level = level
    profile.score = score
    profile.confidence = confidence
    profile.evidence_count = evidence_count

    await db.commit()
    await db.refresh(profile, attribute_names=["capability"])
    return profile


async def list_evidence_for_employee(
    db: AsyncSession, employee_id: str, capability_id: str | None = None
) -> list[CapabilityEvidence]:
    stmt = select(CapabilityEvidence).where(CapabilityEvidence.employee_id == employee_id)
    if capability_id:
        stmt = stmt.where(CapabilityEvidence.capability_id == capability_id)
    stmt = stmt.order_by(CapabilityEvidence.created_at)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_evidence_for_attempt(
    db: AsyncSession,
    mission_attempt_id: str | None = None,
    quest_attempt_id: str | None = None,
) -> list[CapabilityEvidence]:
    """Exactly one of mission_attempt_id/quest_attempt_id must be given —
    mirrors the model's own CHECK constraint (Stage 5)."""
    if (mission_attempt_id is None) == (quest_attempt_id is None):
        raise ValueError("Provide exactly one of mission_attempt_id or quest_attempt_id")
    if mission_attempt_id is not None:
        stmt = select(CapabilityEvidence).where(
            CapabilityEvidence.mission_attempt_id == mission_attempt_id
        )
    else:
        stmt = select(CapabilityEvidence).where(
            CapabilityEvidence.quest_attempt_id == quest_attempt_id
        )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_evidence(
    db: AsyncSession,
    *,
    employee_id: str,
    capability_id: str,
    evidence_type: str,
    observation: str,
    strength: str,
    confidence: float,
    source: str,
    mission_attempt_id: str | None = None,
    quest_attempt_id: str | None = None,
    evaluation_id: str | None = None,
) -> CapabilityEvidence:
    """Exactly one of mission_attempt_id/quest_attempt_id must be given —
    mirrors the model's own CHECK constraint (Stage 5). Mission callers
    are unaffected: they still pass mission_attempt_id as a keyword arg,
    unchanged from Phase 3A."""
    if (mission_attempt_id is None) == (quest_attempt_id is None):
        raise ValueError("Provide exactly one of mission_attempt_id or quest_attempt_id")
    evidence = CapabilityEvidence(
        employee_id=employee_id,
        mission_attempt_id=mission_attempt_id,
        quest_attempt_id=quest_attempt_id,
        capability_id=capability_id,
        evaluation_id=evaluation_id,
        evidence_type=evidence_type,
        observation=observation,
        strength=strength,
        confidence=confidence,
        source=source,
    )
    db.add(evidence)
    await db.commit()
    await db.refresh(evidence)
    return evidence

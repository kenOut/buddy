"""Phase 6D — the persistence layer wrapped around Phase 6C's live
recommendation engine. quest_recommendation.get_next_quest's ranking
algorithm is never modified or re-implemented here; this module only
decides whether a freshly-computed recommendation should be written as a
new historical Recommendation row, or whether the most recent row for
this employee already represents the same context and should be reused
as-is.

    quest_recommendation.get_next_quest (unchanged ranking)
        -> snapshot builder (this module)
        -> context fingerprint (this module)
        -> reuse-or-create against recommendation_service (this module)
        -> NextQuestResponse (built by the endpoint from the result)

Deduplication (Phase 6D Part 6): a context fingerprint is a SHA-256 hash
over (employee_id, recommendation_type, quest_id, sorted target
capabilities, each target capability's level at this moment). If it
matches the employee's single most recent recommendation of this type,
that row is reused unchanged — no new row, no rewritten reason. If it
differs (a different quest is now the best candidate, or the same quest
is recommended but the driving capabilities' levels have moved), a new
historical row is created. This is deliberately NOT a database-level
uniqueness constraint on the hash: the same fingerprint could
legitimately recur far later in an employee's history (development can
genuinely loop back to a similar state), and a hard uniqueness
constraint would wrongly block that later, distinct event. Only the
*latest* row is compared against — full-history hash lookups are not
attempted.
"""

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, Recommendation
from app.services import capability_service, quest_recommendation, recommendation_service

NEXT_QUEST = "NEXT_QUEST"


@dataclass
class PersistedRecommendationResult:
    """What the endpoint actually needs to build a response: the live
    recommendation result (quest/reason/target_capabilities/gap_analysis,
    always freshly computed by the unchanged Phase 6C engine) plus the
    Recommendation row that now represents it in history (None only when
    there was nothing to recommend at all)."""

    quest: object
    reason: str
    target_capabilities: list[str]
    gap_analysis: object
    recommendation: Recommendation | None


def _compute_context_hash(
    employee_id: str,
    recommendation_type: str,
    quest_id: str,
    target_capabilities: list[str],
    capability_snapshot: dict,
) -> str:
    payload = {
        "employee_id": employee_id,
        "recommendation_type": recommendation_type,
        "quest_id": quest_id,
        "target_capabilities": sorted(target_capabilities),
        "levels": {key: capability_snapshot[key]["level"] for key in sorted(capability_snapshot)},
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _build_capability_snapshot(
    db: AsyncSession, employee_id: str, target_capabilities: list[str]
) -> dict:
    """Only snapshots the capabilities that actually drove this
    recommendation — not all six — since those are the only ones the
    persisted `reason` text makes claims about."""
    if not target_capabilities:
        return {}
    profiles = await capability_service.list_profiles_for_employee(db, employee_id)
    by_key = {p.capability.key: p for p in profiles}

    snapshot: dict = {}
    for key in target_capabilities:
        profile = by_key.get(key)
        if profile is None:
            # No CapabilityProfile row yet == NOT_OBSERVED, same default
            # capability_gap_analysis.py already uses for a missing row.
            snapshot[key] = {"level": "NOT_OBSERVED", "score": 0.0, "confidence": 0.0, "evidence_count": 0}
        else:
            snapshot[key] = {
                "level": profile.level,
                "score": float(profile.score),
                "confidence": float(profile.confidence),
                "evidence_count": profile.evidence_count,
            }
    return snapshot


async def get_or_persist_next_quest(db: AsyncSession, employee: Employee) -> PersistedRecommendationResult:
    result = await quest_recommendation.get_next_quest(db, employee)

    if result.quest is None:
        # Nothing to recommend right now — nothing to persist either.
        # This deliberately does NOT touch history: a quiet moment with
        # no candidate is not itself a historical event worth recording.
        return PersistedRecommendationResult(
            quest=None,
            reason=result.reason,
            target_capabilities=[],
            gap_analysis=result.gap_analysis,
            recommendation=None,
        )

    snapshot = await _build_capability_snapshot(db, employee.id, result.target_capabilities)
    context_hash = _compute_context_hash(
        employee.id, NEXT_QUEST, result.quest.id, result.target_capabilities, snapshot
    )

    latest = await recommendation_service.get_latest_for_employee(db, employee.id, NEXT_QUEST)
    if latest is not None and latest.context_hash == context_hash:
        # Same employee, same recommendation type, same quest, same
        # driving capability levels as the last time we checked — this
        # is still the same recommendation event, not a new one. Reuse
        # its persisted reason/snapshot rather than writing a duplicate
        # row or silently rewriting history with a freshly-worded reason.
        return PersistedRecommendationResult(
            quest=result.quest,
            reason=latest.reason,
            target_capabilities=latest.target_capabilities,
            gap_analysis=result.gap_analysis,
            recommendation=latest,
        )

    created = await recommendation_service.create_recommendation(
        db,
        employee_id=employee.id,
        quest_id=result.quest.id,
        recommendation_type=NEXT_QUEST,
        reason=result.reason,
        target_capabilities=result.target_capabilities,
        capability_snapshot=snapshot,
        context_hash=context_hash,
    )
    return PersistedRecommendationResult(
        quest=result.quest,
        reason=created.reason,
        target_capabilities=created.target_capabilities,
        gap_analysis=result.gap_analysis,
        recommendation=created,
    )

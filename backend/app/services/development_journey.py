"""Phase 6D — the Development Journey read model.

Composes existing authoritative sources into one deterministic,
chronologically-ordered timeline. This module writes nothing; it is a
pure read/compose layer over data other services already own:

  A. OnboardingSession completion  (onboarding_service, unmodified)
  B. Completed QuestAttempts        (quest_attempt_service, unmodified)
  C. CapabilityEvidence, grouped    (capability_service, unmodified) —
     one observation per (capability, attempt), not one row per
     evidence_type, so multiple deterministic+AI rows from the same
     evaluation don't render as meaningless duplicates (Phase 6D Part 11)
  D. Persisted Recommendation history (recommendation_service, Phase 6D)
  E. Current readiness state        (readiness_service, Phase 8H-2) —
     a live, current-state-derived indicator, NOT a stored historical
     event; it exists in the timeline only while the employee currently
     satisfies readiness and disappears the moment that stops being
     true (e.g. a new required quest is assigned) — see _readiness_items
     below, and do not describe this item as "first readiness" or an
     immutable milestone anywhere this module is touched
  F. GRANTED WorkspaceAccessGrant rows (Phase 8H-2) — read directly,
     nothing new to reuse a service function for beyond the models
     themselves; employee-safe fields only (display_name/workspace_link),
     never external_ref/provider/provider_ref/last_error/attempt_count

Ordering (Phase 6D Part 10): ascending by timestamp — oldest first. This
matches the product spec's own example timeline, which only reads as a
coherent narrative in forward-time order ("Quest completed -> Capability
observed -> Buddy recommends -> Quest completed" is causally sequential,
not a reverse-chronological feed). Tie-break for identical timestamps is
a fixed event-type priority — the order those events would causally
occur in — then the item's own id as the final, absolute tiebreak.
Database default ordering is never relied upon — everything is sorted
explicitly in Python after all sources are fetched. Phase 8H-2 slots
READINESS_REACHED and WORKSPACE_ACCESS_GRANTED between CAPABILITY_
OBSERVED and RECOMMENDATION for the same reason: the READINESS_REACHED
item's timestamp very often coincides exactly with the QUEST_COMPLETED/
CAPABILITY_OBSERVED items derived from the same attempt (the quest whose
completion currently satisfies the required set), and it causally
follows them when it does appear; workspace access, in turn, is always
causally downstream of readiness when both are present. This ordering
says nothing about READINESS_REACHED being a permanent, once-earned
position in the timeline — it is simply where a currently-present
milestone sorts relative to other items, for as long as it remains
present.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Capability,
    CapabilityEvidence,
    Employee,
    Mission,
    MissionAttempt,
    Quest,
    QuestAttempt,
    Recommendation,
    WorkspaceAccessGrant,
    WorkspaceIntegration,
)
from app.services import (
    capability_service,
    onboarding_service,
    quest_attempt_service,
    readiness_service,
    recommendation_service,
)

ONBOARDING_COMPLETED = "ONBOARDING_COMPLETED"
QUEST_COMPLETED = "QUEST_COMPLETED"
CAPABILITY_OBSERVED = "CAPABILITY_OBSERVED"
READINESS_REACHED = "READINESS_REACHED"
WORKSPACE_ACCESS_GRANTED = "WORKSPACE_ACCESS_GRANTED"
RECOMMENDATION = "RECOMMENDATION"

_TYPE_PRIORITY = {
    ONBOARDING_COMPLETED: 0,
    QUEST_COMPLETED: 1,
    CAPABILITY_OBSERVED: 2,
    READINESS_REACHED: 3,
    WORKSPACE_ACCESS_GRANTED: 4,
    RECOMMENDATION: 5,
}

_STRENGTH_RANK = {"DEVELOPING": 0, "CAPABLE": 1, "STRONG": 2}


@dataclass
class JourneyItem:
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
    workspace_name: str | None = None
    workspace_link: str | None = None


@dataclass
class DevelopmentJourney:
    employee_id: str
    items: list[JourneyItem]


def _attempt_key(evidence: CapabilityEvidence) -> str:
    key = evidence.mission_attempt_id or evidence.quest_attempt_id
    assert key is not None, "CapabilityEvidence row with neither attempt id set"
    return key


def _onboarding_items(session) -> list[JourneyItem]:
    if session is None or session.status != "completed" or session.completed_at is None:
        return []
    return [
        JourneyItem(
            id=f"{ONBOARDING_COMPLETED}:{session.id}",
            type=ONBOARDING_COMPLETED,
            timestamp=session.completed_at,
            title="Onboarding completed",
            description="Buddy guided you through your first steps.",
        )
    ]


def _quest_completion_items(
    quest_attempts: list[QuestAttempt], quest_by_id: dict[str, Quest]
) -> list[JourneyItem]:
    items = []
    for attempt in quest_attempts:
        if attempt.status != "COMPLETED" or attempt.completed_at is None:
            continue
        quest = quest_by_id.get(attempt.quest_id)
        items.append(
            JourneyItem(
                id=f"{QUEST_COMPLETED}:{attempt.id}",
                type=QUEST_COMPLETED,
                timestamp=attempt.completed_at,
                title="Quest completed",
                description=quest.title if quest else "A quest you completed",
                quest_id=attempt.quest_id,
                quest_available=quest is not None and quest.status == "PUBLISHED",
            )
        )
    return items


def _capability_observation_items(
    evidence: list[CapabilityEvidence],
    capability_by_id: dict[str, Capability],
    quest_by_id: dict[str, Quest],
    mission_by_id: dict[str, Mission],
    quest_attempt_by_id: dict[str, QuestAttempt],
    mission_attempt_by_id: dict[str, MissionAttempt],
) -> list[JourneyItem]:
    groups: dict[tuple[str, str], list[CapabilityEvidence]] = {}
    for row in evidence:
        groups.setdefault((row.capability_id, _attempt_key(row)), []).append(row)

    items = []
    for (capability_id, _attempt_id), rows in groups.items():
        # The strongest signal observed in this one evaluation event
        # represents the group — same "collapse same-attempt evidence
        # into one data point" principle capability_aggregation.py
        # already uses for profile rollups, applied here to the journey
        # instead. created_at is the deterministic tiebreak among equal
        # strengths.
        representative = max(
            rows, key=lambda r: (_STRENGTH_RANK.get(r.strength, -1), r.created_at)
        )
        capability = capability_by_id.get(capability_id)
        if capability is None:
            continue

        source_title = None
        if representative.quest_attempt_id:
            qa = quest_attempt_by_id.get(representative.quest_attempt_id)
            if qa is not None:
                quest = quest_by_id.get(qa.quest_id)
                source_title = quest.title if quest else None
        elif representative.mission_attempt_id:
            ma = mission_attempt_by_id.get(representative.mission_attempt_id)
            if ma is not None:
                mission = mission_by_id.get(ma.mission_id)
                source_title = mission.title if mission else None

        description = (
            f'Observed during "{source_title}".' if source_title else "Observed during completed work."
        )

        items.append(
            JourneyItem(
                id=f"{CAPABILITY_OBSERVED}:{representative.id}",
                type=CAPABILITY_OBSERVED,
                timestamp=representative.created_at,
                title=f"{capability.name} — {representative.strength.title()}",
                description=description,
                capability=capability.key,
                level=representative.strength,
            )
        )
    return items


def _recommendation_items(
    recommendations: list[Recommendation], quest_by_id: dict[str, Quest]
) -> list[JourneyItem]:
    items = []
    for rec in recommendations:
        quest = quest_by_id.get(rec.quest_id)
        items.append(
            JourneyItem(
                id=f"{RECOMMENDATION}:{rec.id}",
                type=RECOMMENDATION,
                timestamp=rec.created_at,
                title="Buddy's next recommendation",
                description=quest.title if quest else "A quest that's no longer available",
                quest_id=rec.quest_id,
                quest_available=quest is not None and quest.status == "PUBLISHED",
                reason=rec.reason,
                target_capabilities=list(rec.target_capabilities),
            )
        )
    return items


async def _readiness_items(db: AsyncSession, employee: Employee) -> list[JourneyItem]:
    """Phase 8H-2, corrected — a derived journey milestone representing
    that the employee CURRENTLY satisfies the readiness requirements.
    This is explicitly NOT a historical record and must never be
    described as one: it is not "first readiness," not "the moment the
    employee became ready," and not an immutable or permanently-retained
    event. There is no persisted readiness history anywhere in this
    system, so no code path — this one included — can honestly answer
    "when did this employee first become ready"; this function only
    ever answers "are they ready right now, and if so, what timestamp
    goes with today's requirement set" (see readiness_service.
    get_readiness_milestone_timestamp's own docstring for that
    computation).

    Calls is_ready() unchanged (via get_readiness_milestone_timestamp)
    and reuses the exact same eligibility resolution is_ready() already
    uses — no second, independently-derived notion of readiness.
    Produces at most one item, since there is only ever one "currently
    ready" state to represent, not one per required quest. Its id is
    deterministic per employee (not tied to any stored row), so repeated
    calls against unchanged data produce the identical item every time —
    and the item correctly disappears from the timeline the moment the
    employee is no longer currently ready (e.g. a new required quest is
    assigned, or the quest that had satisfied the set is archived). That
    disappearance is intended, correct behavior: showing a "ready" item
    for an employee who is not currently ready would be a false claim,
    and this codebase has no historical record that could justify
    keeping it around regardless."""
    timestamp = await readiness_service.get_readiness_milestone_timestamp(db, employee)
    if timestamp is None:
        return []
    return [
        JourneyItem(
            id=f"{READINESS_REACHED}:{employee.id}",
            type=READINESS_REACHED,
            timestamp=timestamp,
            title="Ready to work",
            description="You completed your required onboarding and work — Buddy considers you ready.",
        )
    ]


async def _workspace_access_items(
    db: AsyncSession, employee_id: str
) -> list[JourneyItem]:
    """Phase 8H-2 — read directly from WorkspaceAccessGrant/
    WorkspaceIntegration; only `status == "GRANTED"` rows produce an
    item (PENDING/FAILED/REVOKED never do — see Step 10). Uses
    `granted_at` as the event timestamp, never `created_at`/
    `requested_at`, so the journey shows when access actually became
    real, not when it was first attempted. One item per grant row — the
    existing UNIQUE(employee_id, workspace_integration_id) constraint is
    exactly what prevents duplicates here; if an employee ever
    legitimately holds grants against multiple WorkspaceIntegrations
    (the data model permits it even though today's trigger only ever
    creates one per employee), each produces its own distinguishable
    item rather than collapsing into one."""
    stmt = (
        select(WorkspaceAccessGrant, WorkspaceIntegration)
        .join(WorkspaceIntegration, WorkspaceIntegration.id == WorkspaceAccessGrant.workspace_integration_id)
        .where(
            WorkspaceAccessGrant.employee_id == employee_id,
            WorkspaceAccessGrant.status == "GRANTED",
        )
    )
    result = await db.execute(stmt)

    items = []
    for grant, integration in result.all():
        if grant.granted_at is None:
            # Defensive only: a GRANTED row should always have
            # granted_at set (workspace_access_service sets both
            # together) — never fabricate a timestamp if this
            # invariant is somehow violated.
            continue
        items.append(
            JourneyItem(
                id=f"{WORKSPACE_ACCESS_GRANTED}:{grant.id}",
                type=WORKSPACE_ACCESS_GRANTED,
                timestamp=grant.granted_at,
                title="Workspace access granted",
                description=f"You now have access to {integration.display_name}.",
                workspace_name=integration.display_name,
                workspace_link=integration.workspace_link,
            )
        )
    return items


async def build_journey(db: AsyncSession, employee: Employee) -> DevelopmentJourney:
    quest_attempts = await quest_attempt_service.list_attempts_for_employee(db, employee.id)
    recommendations = await recommendation_service.list_for_employee(db, employee.id)
    evidence = await capability_service.list_evidence_for_employee(db, employee.id)
    session = await onboarding_service.get_or_create_session(db, employee)

    # Bulk-resolve every referenced Quest/Mission/attempt up front —
    # never one query per item.
    quest_ids = {a.quest_id for a in quest_attempts} | {r.quest_id for r in recommendations}

    quest_attempt_ids = {e.quest_attempt_id for e in evidence if e.quest_attempt_id}
    quest_attempt_by_id = {a.id: a for a in quest_attempts}
    missing_qa_ids = quest_attempt_ids - set(quest_attempt_by_id)
    if missing_qa_ids:
        result = await db.execute(select(QuestAttempt).where(QuestAttempt.id.in_(missing_qa_ids)))
        for a in result.scalars().all():
            quest_attempt_by_id[a.id] = a
    quest_ids |= {a.quest_id for a in quest_attempt_by_id.values()}

    mission_attempt_ids = {e.mission_attempt_id for e in evidence if e.mission_attempt_id}
    mission_attempt_by_id: dict[str, MissionAttempt] = {}
    if mission_attempt_ids:
        result = await db.execute(select(MissionAttempt).where(MissionAttempt.id.in_(mission_attempt_ids)))
        for a in result.scalars().all():
            mission_attempt_by_id[a.id] = a
    mission_ids = {a.mission_id for a in mission_attempt_by_id.values()}

    quest_by_id: dict[str, Quest] = {}
    if quest_ids:
        result = await db.execute(select(Quest).where(Quest.id.in_(quest_ids)))
        for q in result.scalars().all():
            quest_by_id[q.id] = q

    mission_by_id: dict[str, Mission] = {}
    if mission_ids:
        result = await db.execute(select(Mission).where(Mission.id.in_(mission_ids)))
        for m in result.scalars().all():
            mission_by_id[m.id] = m

    capabilities = await capability_service.list_capabilities(db)
    capability_by_id = {c.id: c for c in capabilities}

    items: list[JourneyItem] = []
    items += _onboarding_items(session)
    items += _quest_completion_items(quest_attempts, quest_by_id)
    items += _capability_observation_items(
        evidence, capability_by_id, quest_by_id, mission_by_id, quest_attempt_by_id, mission_attempt_by_id
    )
    items += await _readiness_items(db, employee)
    items += await _workspace_access_items(db, employee.id)
    items += _recommendation_items(recommendations, quest_by_id)

    items.sort(key=lambda it: (it.timestamp, _TYPE_PRIORITY[it.type], it.id))

    return DevelopmentJourney(employee_id=employee.id, items=items)

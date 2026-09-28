"""Phase 6C Stages 3-5 — deterministic "what Quest should this employee
try next" logic. Mirrors mission_recommendation.py's shape exactly: no
LLM, no randomness, no timestamps used for ranking — the same inputs
always produce the same output, which is what makes GET /next-quest
callable repeatedly and testable.

The core loop this closes:

    Quest -> QuestAttempt -> Evaluation -> CapabilityEvidence
    -> CapabilityProfile -> Capability Gap Analysis -> Next Quest Recommendation

Every existing safety rail stays authoritative and is re-used, not
re-implemented:
  - quest.status == "PUBLISHED" is checked directly (DRAFT/ARCHIVED never
    considered — same rule quest_assignment_service.is_employee_eligible
    already enforces, checked again here defensively).
  - quest_assignment_service.is_employee_eligible is THE eligibility
    check — this module never reasons about assignment types itself.
  - A quest the employee already has a COMPLETED attempt for is excluded
    outright (Stage 3 spec — no repetition support exists yet).
"""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, Quest
from app.models.quest import QUEST_DIFFICULTIES
from app.services import (
    capability_gap_analysis,
    quest_assignment_service,
    quest_attempt_service,
    quest_capability_service,
    quest_service,
)
from app.services.capability_gap_analysis import CapabilityGapAnalysis, CapabilityGapItem

DIFFICULTY_RANK = {d: i for i, d in enumerate(QUEST_DIFFICULTIES)}

# Lower tier number = higher recommendation priority (Phase 6C Stage 3):
# a quest touching even one DEVELOPING capability always outranks one
# that only touches CAPABLE/STRONG capabilities, regardless of what else
# it maps to.
_TIER_DEVELOPING = 0
_TIER_UNOBSERVED = 1
_TIER_CAPABLE = 2
_TIER_STRONG = 3

_RELEVANT_LEVELS = {"DEVELOPING", "NOT_OBSERVED"}


@dataclass
class QuestRecommendationResult:
    quest: Quest | None
    reason: str
    target_capabilities: list[str] = field(default_factory=list)
    gap_analysis: CapabilityGapAnalysis | None = None


@dataclass
class _Candidate:
    quest: Quest
    mapped_items: list[CapabilityGapItem]  # this quest's mapped capabilities, with the employee's current level attached
    tier: int


def _tier_for(mapped_items: list[CapabilityGapItem]) -> int:
    levels = {item.current_level for item in mapped_items}
    if "DEVELOPING" in levels:
        return _TIER_DEVELOPING
    if "NOT_OBSERVED" in levels:
        return _TIER_UNOBSERVED
    if "CAPABLE" in levels:
        return _TIER_CAPABLE
    return _TIER_STRONG


def _relevant_count(mapped_items: list[CapabilityGapItem]) -> int:
    return sum(1 for item in mapped_items if item.current_level in _RELEVANT_LEVELS)


def _sort_key(candidate: _Candidate) -> tuple:
    quest = candidate.quest
    return (
        candidate.tier,
        -_relevant_count(candidate.mapped_items),
        DIFFICULTY_RANK.get(quest.difficulty, len(QUEST_DIFFICULTIES)),
        quest.quest_type,
        quest.created_at,
        quest.id,
    )


def _join(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def _build_reason(candidate: _Candidate) -> tuple[str, list[str]]:
    """Returns (reason, target_capability_keys). target_capabilities is
    the set of mapped capabilities that actually drove the selection at
    this quest's tier — never every capability the quest happens to map
    to, so the explanation never overstates what's relevant."""
    by_level: dict[str, list[CapabilityGapItem]] = {}
    for item in candidate.mapped_items:
        by_level.setdefault(item.current_level, []).append(item)

    developing = by_level.get("DEVELOPING", [])
    unobserved = by_level.get("NOT_OBSERVED", [])
    capable = by_level.get("CAPABLE", [])
    strong = by_level.get("STRONG", [])

    if candidate.tier == _TIER_DEVELOPING:
        dev_names = [i.capability_name for i in developing]
        verb = "is" if len(dev_names) == 1 else "are"
        reason = (
            f"This Quest gives you an opportunity to strengthen {_join(dev_names)}, "
            f"which {verb} currently developing."
        )
        if capable:
            cap_names = [i.capability_name for i in capable]
            reason += f" It also builds on your existing {_join(cap_names)} capability."
        return reason, [i.capability_key for i in developing]

    if candidate.tier == _TIER_UNOBSERVED:
        names = [i.capability_name for i in unobserved]
        verb = "hasn't" if len(names) == 1 else "haven't"
        reason = (
            f"This Quest introduces evidence collection for {_join(names)}, which {verb} been "
            "observed yet."
        )
        return reason, [i.capability_key for i in unobserved]

    if candidate.tier == _TIER_CAPABLE:
        names = [i.capability_name for i in capable]
        reason = f"This Quest builds on your current {_join(names)} capability."
        return reason, [i.capability_key for i in capable]

    # _TIER_STRONG — every mapped capability is already STRONG.
    names = [i.capability_name for i in strong]
    reason = (
        f"This Quest is available and relates to {_join(names)}, where you're already strong — "
        "a solid option if nothing else fits right now."
    )
    return reason, [i.capability_key for i in strong]


async def get_next_quest(db: AsyncSession, employee: Employee) -> QuestRecommendationResult:
    gap_analysis = await capability_gap_analysis.analyze_gaps(db, employee.id)
    level_by_key = {item.capability_key: item.current_level for item in gap_analysis.assessed_capabilities}

    all_quests = await quest_service.list_quests(db)
    published = [q for q in all_quests if q.status == "PUBLISHED"]

    if not published:
        return QuestRecommendationResult(
            quest=None,
            reason="No suitable published Quest is currently available.",
            gap_analysis=gap_analysis,
        )

    attempts = await quest_attempt_service.list_attempts_for_employee(db, employee.id)
    completed_quest_ids = {a.quest_id for a in attempts if a.status == "COMPLETED"}

    candidates: list[_Candidate] = []
    for quest in published:
        if quest.id in completed_quest_ids:
            continue

        eligibility = await quest_assignment_service.is_employee_eligible(db, quest, employee)
        if not eligibility.eligible:
            continue

        mappings = await quest_capability_service.list_mappings(db, quest.id)
        if not mappings:
            # Defensive only — Phase 6B's publish validation already
            # requires >=1 capability mapping, so a PUBLISHED quest with
            # none shouldn't exist. If it somehow does (legacy data),
            # there's nothing honest to recommend it *for*.
            continue

        mapped_items = [
            CapabilityGapItem(
                capability_key=m.capability.key,
                capability_name=m.capability.name,
                current_level=level_by_key.get(m.capability.key, "NOT_OBSERVED"),
                category="",
                reason="",
            )
            for m in mappings
        ]
        tier = _tier_for(mapped_items)
        candidates.append(_Candidate(quest=quest, mapped_items=mapped_items, tier=tier))

    if not candidates:
        return QuestRecommendationResult(
            quest=None,
            reason="No suitable published Quest is currently available.",
            gap_analysis=gap_analysis,
        )

    best = min(candidates, key=_sort_key)
    reason, target_capabilities = _build_reason(best)

    return QuestRecommendationResult(
        quest=best.quest,
        reason=reason,
        target_capabilities=target_capabilities,
        gap_analysis=gap_analysis,
    )

"""Deterministic "what should this employee work on next" logic.

No LLM decides the next mission — this reads plain, inspectable state
(assignments, capability profiles) and applies fixed rules. Two cases:

1. An investigation mission (one with a scenario in mission_scenarios.py,
   i.e. one that actually produces capability evidence) is still
   available -> recommend it, and name the capabilities it's most likely
   to move for THIS employee: their weakest capabilities among the ones
   that mission's deterministic evidence rules can touch at all. This
   keeps `target_capabilities` honest — never a capability the mission
   can't actually produce evidence for.
2. Otherwise -> recommend the next incomplete onboarding task in its
   existing sort order (a checklist item doesn't build capability
   evidence, so `target_capabilities` is empty rather than guessed).

If nothing is left, returns (mission=None, reason=..., target_capabilities=[]).
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CAPABILITY_LEVELS, Mission
from app.services import capability_service, mission_scenarios, mission_service
from app.services.capability_evidence_pipeline import DETERMINISTIC_EVIDENCE_RULES

LEVEL_RANK = {level: i for i, level in enumerate(CAPABILITY_LEVELS)}


@dataclass
class RecommendationResult:
    mission: Mission | None
    reason: str
    target_capabilities: list[str]


async def _weakest_capability_keys(db: AsyncSession, employee_id: str, candidates: set[str]) -> list[str]:
    """Among `candidates` (capability keys), returns them ordered weakest
    (lowest level, then lowest confidence) first. A capability the
    employee has no profile row for yet is NOT_OBSERVED — the weakest
    possible standing, not a penalty."""
    if not candidates:
        return []

    profiles = await capability_service.list_profiles_for_employee(db, employee_id)
    by_key = {p.capability.key: p for p in profiles}

    def sort_key(key: str) -> tuple[int, float]:
        profile = by_key.get(key)
        if profile is None:
            return (LEVEL_RANK["NOT_OBSERVED"], 0.0)
        return (LEVEL_RANK[profile.level], float(profile.confidence))

    return sorted(candidates, key=sort_key)


def _capabilities_touched_by_mission(mission: Mission) -> set[str]:
    scenario = mission_scenarios.get_scenario(mission.title)
    if scenario is None:
        return set()
    touched: set[str] = set()
    for rules in DETERMINISTIC_EVIDENCE_RULES.values():
        touched.update(key for key, _ in rules)
    return touched


async def get_next_mission(db: AsyncSession, employee_id: str) -> RecommendationResult:
    assignments = await mission_service.list_assignments_for_employee(db, employee_id)
    available = [a for a in assignments if a.status != "completed"]

    if not available:
        return RecommendationResult(
            mission=None,
            reason="All assigned missions are complete — nothing left to recommend right now.",
            target_capabilities=[],
        )

    investigation_assignments = [a for a in available if mission_scenarios.get_scenario(a.mission.title)]
    if investigation_assignments:
        assignment = investigation_assignments[0]
        mission = assignment.mission
        touched = _capabilities_touched_by_mission(mission)
        weakest = await _weakest_capability_keys(db, employee_id, touched)
        target = weakest[:3]
        return RecommendationResult(
            mission=mission,
            reason=(
                f"\"{mission.title}\" is a hands-on investigation — a good next step to build on "
                f"{', '.join(k.replace('_', ' ') for k in target)}."
                if target
                else f"\"{mission.title}\" is the next available investigation mission."
            ),
            target_capabilities=target,
        )

    assignment = available[0]
    return RecommendationResult(
        mission=assignment.mission,
        reason=f"\"{assignment.mission.title}\" is the next step in your onboarding checklist.",
        target_capabilities=[],
    )

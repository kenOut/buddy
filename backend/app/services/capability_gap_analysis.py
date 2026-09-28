"""Phase 6C Stage 2 — deterministic Capability Gap Analysis.

Turns an employee's existing CapabilityProfile rows into a structured,
explainable picture of where they stand: strengths, development areas,
unobserved capabilities, and the full assessed set. No scores are
invented here — this reads CapabilityProfile.level exactly as
capability_aggregation.py already computed it and classifies each of the
6 capabilities into exactly one of four categories.

NOT_OBSERVED is never collapsed into DEVELOPING: "no evidence yet" and
"evidence shows this needs work" are different claims, and conflating
them would make the reason text lie about what Buddy actually observed.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Capability
from app.services import capability_service

STRENGTH = "STRENGTH"
CAPABLE_CATEGORY = "CAPABLE"
DEVELOPMENT_AREA = "DEVELOPMENT_AREA"
UNOBSERVED = "UNOBSERVED"

_CATEGORY_BY_LEVEL = {
    "STRONG": STRENGTH,
    "CAPABLE": CAPABLE_CATEGORY,
    "DEVELOPING": DEVELOPMENT_AREA,
    "NOT_OBSERVED": UNOBSERVED,
}

_REASON_BY_LEVEL = {
    "STRONG": "Repeated evidence across completed work shows consistent strength here.",
    "CAPABLE": "Evidence shows solid capability here — not currently a priority development area.",
    "DEVELOPING": "Evidence so far is limited — a good candidate for focused development.",
    "NOT_OBSERVED": "No evidence has been observed yet for this capability.",
}


@dataclass
class CapabilityGapItem:
    capability_key: str
    capability_name: str
    current_level: str
    category: str
    reason: str


@dataclass
class CapabilityGapAnalysis:
    employee_id: str
    strengths: list[CapabilityGapItem] = field(default_factory=list)
    development_areas: list[CapabilityGapItem] = field(default_factory=list)
    unobserved: list[CapabilityGapItem] = field(default_factory=list)
    assessed_capabilities: list[CapabilityGapItem] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _item_for(capability: Capability, level: str) -> CapabilityGapItem:
    return CapabilityGapItem(
        capability_key=capability.key,
        capability_name=capability.name,
        current_level=level,
        category=_CATEGORY_BY_LEVEL[level],
        reason=_REASON_BY_LEVEL[level],
    )


async def analyze_gaps(db: AsyncSession, employee_id: str) -> CapabilityGapAnalysis:
    """Every capability in the global taxonomy gets exactly one entry in
    `assessed_capabilities`, whether or not the employee has a
    CapabilityProfile row for it yet (no row = NOT_OBSERVED, the same
    default CapabilityProfile itself uses) — so callers never have to
    special-case "missing profile" separately from "profile says
    NOT_OBSERVED"."""
    all_capabilities = await capability_service.list_capabilities(db)
    profiles = await capability_service.list_profiles_for_employee(db, employee_id)
    level_by_capability_id = {p.capability_id: p.level for p in profiles}

    analysis = CapabilityGapAnalysis(employee_id=employee_id)
    for capability in all_capabilities:
        level = level_by_capability_id.get(capability.id, "NOT_OBSERVED")
        item = _item_for(capability, level)
        analysis.assessed_capabilities.append(item)
        if item.category == STRENGTH:
            analysis.strengths.append(item)
        elif item.category == DEVELOPMENT_AREA:
            analysis.development_areas.append(item)
        elif item.category == UNOBSERVED:
            analysis.unobserved.append(item)
        # CAPABLE items live only in assessed_capabilities — "demonstrated
        # capability, not necessarily a gap" (Phase 6C Stage 2 spec).

    return analysis

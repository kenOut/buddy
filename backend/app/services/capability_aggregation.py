"""Deterministic, documented rules for turning a set of CapabilityEvidence
rows into a CapabilityProfile (level, score, confidence, evidence_count).

Aggregation happens in two steps:

1. Per-attempt summary: all evidence rows for one capability *within one
   mission attempt* collapse into a single (strength, confidence) pair for
   that attempt. Several evidence_types confirming the same capability in
   one investigation is one data point, not several independent ones.
2. Cross-attempt aggregation: the per-attempt summaries combine using the
   rules below. "Repeated" means evidence from *distinct* mission
   attempts — one good result, however strong, isn't proof by itself;
   proof comes from repetition across separate missions.

Level rules:
    0 attempts with evidence           -> NOT_OBSERVED
    1 attempt with evidence            -> DEVELOPING
    >=2 attempts, mostly CAPABLE+      -> CAPABLE
    >=2 attempts, mostly STRONG,
        average confidence >= 0.6      -> STRONG
    >=2 attempts, mixed/weak           -> DEVELOPING

`score` is a transparent numeric echo of those same per-attempt strengths
(DEVELOPING=40, CAPABLE=70, STRONG=95), plain-averaged across attempts —
never a separately-tuned number that could disagree with `level`.

`confidence` is the plain mean of each attempt's evidence confidence — no
hidden boosting for "more data," so it stays inspectable. `evidence_count`
is the raw number of underlying CapabilityEvidence rows (not attempts),
so it's a literal, checkable count.
"""

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CapabilityEvidence, CapabilityProfile
from app.services import capability_service

STRENGTH_SCORE = {"DEVELOPING": 40.0, "CAPABLE": 70.0, "STRONG": 95.0}
STRENGTH_RANK = {"DEVELOPING": 0, "CAPABLE": 1, "STRONG": 2}


@dataclass
class AggregationResult:
    level: str
    score: float
    confidence: float
    evidence_count: int


def _attempt_key(evidence_row: CapabilityEvidence) -> str:
    """The evidence's source attempt, regardless of type — exactly one of
    mission_attempt_id/quest_attempt_id is populated on any given row
    (Stage 5), so this is never ambiguous. Grouping by this instead of
    the raw mission_attempt_id column matters: every quest-sourced row
    has mission_attempt_id = None, so grouping by that column alone would
    collapse every quest attempt's evidence into a single None bucket —
    "repeated evidence" from 3 different quests would look identical to
    3 evidence rows from 1 quest."""
    key = evidence_row.mission_attempt_id or evidence_row.quest_attempt_id
    assert key is not None, "CapabilityEvidence row with neither attempt id set (violates CHECK constraint)"
    return key


def _per_attempt_summary(evidence: list[CapabilityEvidence]) -> dict[str, tuple[str, float]]:
    """attempt id (mission or quest) -> (strongest strength observed in
    that attempt, mean confidence of that attempt's evidence for this
    capability)."""
    by_attempt: dict[str, list[CapabilityEvidence]] = defaultdict(list)
    for e in evidence:
        by_attempt[_attempt_key(e)].append(e)

    summary: dict[str, tuple[str, float]] = {}
    for attempt_id, rows in by_attempt.items():
        strongest = max(rows, key=lambda r: STRENGTH_RANK[r.strength]).strength
        mean_confidence = sum(float(r.confidence) for r in rows) / len(rows)
        summary[attempt_id] = (strongest, mean_confidence)
    return summary


def aggregate(evidence: list[CapabilityEvidence]) -> AggregationResult:
    if not evidence:
        return AggregationResult(level="NOT_OBSERVED", score=0.0, confidence=0.0, evidence_count=0)

    per_attempt = _per_attempt_summary(evidence)
    attempts = list(per_attempt.values())  # [(strength, confidence), ...]
    num_attempts = len(attempts)

    mean_confidence = sum(c for _, c in attempts) / num_attempts
    mean_score = sum(STRENGTH_SCORE[s] for s, _ in attempts) / num_attempts

    if num_attempts == 1:
        level = "DEVELOPING"
    else:
        strong_count = sum(1 for s, _ in attempts if s == "STRONG")
        capable_or_better = sum(1 for s, _ in attempts if s in ("CAPABLE", "STRONG"))

        if strong_count >= (num_attempts / 2) and mean_confidence >= 0.6:
            level = "STRONG"
        elif capable_or_better >= (num_attempts / 2):
            level = "CAPABLE"
        else:
            level = "DEVELOPING"

    return AggregationResult(
        level=level,
        score=round(mean_score, 1),
        confidence=round(mean_confidence, 3),
        evidence_count=len(evidence),
    )


async def recompute_profile(
    db: AsyncSession, employee_id: str, capability_id: str
) -> CapabilityProfile:
    """The integration point: fetch all evidence for this (employee,
    capability) — the single source of truth — apply the deterministic
    rules above, and upsert the profile. Never called with fabricated or
    partial evidence."""
    evidence = await capability_service.list_evidence_for_employee(db, employee_id, capability_id)
    result = aggregate(evidence)
    return await capability_service.upsert_profile(
        db,
        employee_id,
        capability_id,
        level=result.level,
        score=result.score,
        confidence=result.confidence,
        evidence_count=result.evidence_count,
    )


async def recompute_profiles_for_evidence(
    db: AsyncSession, employee_id: str, evidence_rows: list[CapabilityEvidence]
) -> list[CapabilityProfile]:
    """Convenience wrapper: recompute only the profiles actually touched
    by a batch of newly-created evidence, instead of all 6 capabilities
    unconditionally."""
    capability_ids = {e.capability_id for e in evidence_rows}
    return [await recompute_profile(db, employee_id, cap_id) for cap_id in capability_ids]

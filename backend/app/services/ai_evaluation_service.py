"""Orchestrates AI interpretation of a completed mission attempt.

AI response -> Pydantic validation -> INVALID -> nothing is persisted.
This module is the enforcement point for that rule: a malformed or
out-of-contract response never reaches CapabilityEvaluation or
CapabilityEvidence.
"""

import json

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import CapabilityEvaluation, CapabilityEvidence, Employee, Mission, MissionAttempt
from app.schemas.ai_evaluation import AIEvaluationResponse
from app.services import capability_aggregation, capability_service, mission_scenarios
from app.services.ai_provider import AIEvaluationContext, AIProviderError, get_ai_provider


class AIEvaluationRejected(Exception):
    """The provider responded, but the response failed schema validation
    (malformed JSON or an out-of-contract shape). Nothing was persisted."""


async def get_evaluation_for_attempt(
    db: AsyncSession, mission_attempt_id: str
) -> CapabilityEvaluation | None:
    stmt = select(CapabilityEvaluation).where(
        CapabilityEvaluation.mission_attempt_id == mission_attempt_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _build_context(employee: Employee, mission: Mission, attempt: MissionAttempt) -> AIEvaluationContext:
    """Only evidence that actually exists — no hidden answer key. The
    objective result is handed over as an already-decided fact for the AI
    to interpret, never a question for it to re-grade."""
    scenario = mission_scenarios.get_scenario(mission.title)
    briefing = scenario["briefing"] if scenario else (mission.description or "")
    return AIEvaluationContext(
        employee_job_title=employee.job_title,
        mission_title=mission.title,
        mission_briefing=briefing,
        affected_service=attempt.affected_service or "",
        likely_cause=attempt.likely_cause or "",
        reasoning=attempt.reasoning or "",
        evidence_viewed=list(attempt.evidence_viewed or []),
        objective_passed=bool(attempt.passed),
        objective_score=float(attempt.score or 0),
    )


async def _create_ai_evidence(
    db: AsyncSession,
    employee: Employee,
    attempt: MissionAttempt,
    evaluation: CapabilityEvaluation,
    validated: AIEvaluationResponse,
) -> list[CapabilityEvidence]:
    created: list[CapabilityEvidence] = []
    for assessment in validated.capabilities:
        capability = await capability_service.get_capability_by_key(db, assessment.capability)
        if capability is None:
            continue  # defensive; schema validation already guarantees a known key
        row = await capability_service.create_evidence(
            db,
            employee_id=employee.id,
            mission_attempt_id=attempt.id,
            capability_id=capability.id,
            evidence_type="ai_interpretation",
            observation=assessment.evidence,
            strength=assessment.level,
            confidence=assessment.confidence,
            source="ai",
            evaluation_id=evaluation.id,
        )
        created.append(row)
    return created


async def evaluate_attempt(
    db: AsyncSession, employee: Employee, mission: Mission, attempt: MissionAttempt
) -> CapabilityEvaluation:
    """Idempotent: at most one evaluation per mission attempt. Calling
    this again returns the existing record rather than re-invoking the
    provider or duplicating evidence."""
    if attempt.status != "completed":
        raise ValueError("Cannot evaluate a mission attempt that hasn't completed.")

    existing = await get_evaluation_for_attempt(db, attempt.id)
    if existing:
        # Guards against a partial failure between committing the
        # evaluation and creating its evidence rows on a prior call.
        existing_evidence = await capability_service.list_evidence_for_attempt(db, attempt.id)
        if not any(e.evaluation_id == existing.id for e in existing_evidence):
            validated = AIEvaluationResponse.model_validate(existing.structured_result)
            new_evidence = await _create_ai_evidence(db, employee, attempt, existing, validated)
            await capability_aggregation.recompute_profiles_for_evidence(db, employee.id, new_evidence)
        return existing

    settings = get_settings()
    provider = get_ai_provider(settings.ai_provider)
    context = _build_context(employee, mission, attempt)

    # AIProviderError (unavailable/timeout) is allowed to bubble up as-is —
    # the API layer maps it to a recoverable "still analyzing" state
    # without touching the mission attempt's completed status.
    raw_response = await provider.generate(context)

    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise AIEvaluationRejected(f"AI response was not valid JSON: {exc}") from exc

    try:
        validated = AIEvaluationResponse.model_validate(parsed)
    except ValidationError as exc:
        raise AIEvaluationRejected(f"AI response failed schema validation: {exc}") from exc

    evaluation = CapabilityEvaluation(
        mission_attempt_id=attempt.id,
        employee_id=employee.id,
        model=provider.model_name,
        prompt_version=settings.ai_prompt_version,
        evaluation_version=settings.ai_evaluation_version,
        raw_response=raw_response,
        structured_result=validated.model_dump(),
    )
    # Captured before the commit attempt: a rollback expires every
    # attribute on `attempt` (and `evaluation`), so touching attempt.id
    # afterward would trigger an implicit lazy-load outside of an awaited
    # context and blow up with a MissingGreenlet error.
    attempt_id = attempt.id

    db.add(evaluation)
    try:
        await db.commit()
    except IntegrityError:
        # Lost a race with a concurrent evaluate call for the same
        # attempt — same pattern as MissionAttempt/CapabilityProfile.
        await db.rollback()
        existing = await get_evaluation_for_attempt(db, attempt_id)
        if existing:
            return existing
        raise
    await db.refresh(evaluation)

    new_evidence = await _create_ai_evidence(db, employee, attempt, evaluation, validated)
    await capability_aggregation.recompute_profiles_for_evidence(db, employee.id, new_evidence)

    return evaluation

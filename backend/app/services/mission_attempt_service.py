from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Mission, MissionAttempt
from app.schemas.mission_attempt import MissionAttemptSubmit, MissionAttemptUpdate
from app.services import (
    capability_aggregation,
    capability_evidence_pipeline,
    mission_quizzes,
    mission_scenarios,
    mission_service,
)

# The real-effort bar for a reflection-workspace submission — deliberately
# the same length AIProvider._bucket_reasoning_quality already calls
# "CAPABLE" (not the lower DEVELOPING floor), so the one deterministic
# gate this codebase has for "is there a genuine answer here" agrees with
# what the mock AI provider would itself call a substantive explanation,
# rather than inventing a second, different number for the same question.
MIN_REFLECTION_LENGTH = 40


async def get_public_scenario(db: AsyncSession, mission: Mission) -> dict | None:
    """The evidence shown to the employee — deliberately excludes
    `correct_service` / `correct_cause`, which never leave mission_scenarios.py."""
    scenario = mission_scenarios.get_scenario(mission.title)
    if scenario is None:
        return None

    return {
        "mission_id": mission.id,
        "briefing": scenario["briefing"],
        "metrics": scenario["evidence"]["metrics"],
        "logs": scenario["evidence"]["logs"],
        "services": scenario["evidence"]["services"],
        "timeline": scenario["evidence"]["timeline"],
        "service_options": scenario["service_options"],
        "cause_options": scenario["cause_options"],
    }


async def get_public_quiz(db: AsyncSession, mission: Mission) -> dict | None:
    """The quiz shown to the employee — deliberately excludes
    `correct_option`, which never leaves mission_quizzes.py."""
    quiz = mission_quizzes.get_quiz(mission.title)
    if quiz is None:
        return None

    return {
        "mission_id": mission.id,
        "briefing": quiz["briefing"],
        "questions": [
            {"id": q["id"], "prompt": q["prompt"], "options": q["options"]} for q in quiz["questions"]
        ],
    }


async def get_attempt(db: AsyncSession, mission_id: str, employee_id: str) -> MissionAttempt | None:
    stmt = select(MissionAttempt).where(
        MissionAttempt.mission_id == mission_id,
        MissionAttempt.employee_id == employee_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_attempts_for_employee(db: AsyncSession, employee_id: str) -> list[MissionAttempt]:
    """Bulk, not per-mission — mirrors quest_attempt_service.list_attempts_for_employee
    exactly, for the same reason: a caller building a per-employee summary across
    every assigned Mission (e.g. manager_performance_service) must not issue one
    query per Mission to get there."""
    stmt = select(MissionAttempt).where(MissionAttempt.employee_id == employee_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_attempt_by_id(db: AsyncSession, attempt_id: str) -> MissionAttempt | None:
    return await db.get(MissionAttempt, attempt_id)


async def get_or_create_attempt(db: AsyncSession, mission_id: str, employee_id: str) -> MissionAttempt:
    """Upserts the single (mission, employee) row — calling this again for
    an already-started mission just returns the existing attempt, so
    reopening a mission can never create a duplicate.

    The check-then-insert below isn't atomic, so two concurrent calls (e.g.
    a React effect firing twice, or a page double-loaded) can both pass the
    "does it exist?" check before either commits. Rather than lock the
    table, we let the database's own unique constraint be the tiebreaker:
    if we lose that race, we roll back and return the row the other
    request created instead of raising.
    """
    attempt = await get_attempt(db, mission_id, employee_id)
    if attempt:
        return attempt

    attempt = MissionAttempt(
        mission_id=mission_id,
        employee_id=employee_id,
        status="in_progress",
        started_at=datetime.now(timezone.utc),
    )
    db.add(attempt)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await get_attempt(db, mission_id, employee_id)
        if existing is not None:
            return existing
        raise
    await db.refresh(attempt)

    assignment = await mission_service.get_assignment_for_employee_mission(db, mission_id, employee_id)
    if assignment and assignment.status == "pending":
        await mission_service.update_assignment_status(db, assignment, "in_progress")

    return attempt


def _merge_evidence(existing: list[str], incoming: list[str] | None) -> list[str]:
    if not incoming:
        return existing
    seen = set(existing)
    merged = list(existing)
    for item in incoming:
        if item not in seen:
            merged.append(item)
            seen.add(item)
    return merged


async def update_attempt(
    db: AsyncSession, attempt: MissionAttempt, payload: MissionAttemptUpdate
) -> MissionAttempt:
    if payload.affected_service is not None:
        attempt.affected_service = payload.affected_service
    if payload.likely_cause is not None:
        attempt.likely_cause = payload.likely_cause
    if payload.reasoning is not None:
        attempt.reasoning = payload.reasoning
    if payload.quiz_answers is not None:
        attempt.quiz_answers = {**attempt.quiz_answers, **payload.quiz_answers}
    attempt.evidence_viewed = _merge_evidence(attempt.evidence_viewed, payload.evidence_viewed)

    if attempt.status == "not_started":
        attempt.status = "in_progress"
        attempt.started_at = attempt.started_at or datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(attempt)
    return attempt


def _grade_reflection(reasoning: str | None) -> tuple[float, bool, str]:
    """Deterministic completion gate for a reflection-workspace mission —
    there's no objectively correct answer to check, so this asks a
    narrower, honest question instead: did the employee actually write a
    real submission, not "yes I did it." See MIN_REFLECTION_LENGTH's own
    docstring for why that specific bar. Passing here only means the
    mission is genuinely complete; the qualitative read on WHAT was
    written is the AI provider's job, run afterward, never this one's."""
    text = (reasoning or "").strip()
    if len(text) >= MIN_REFLECTION_LENGTH:
        return 100.0, True, "Nice work — that's a real, specific description of what you did."
    return (
        0.0,
        False,
        f"Add a bit more detail — at least {MIN_REFLECTION_LENGTH} characters describing what you "
        "actually did, not just that you did it.",
    )


async def submit_attempt(
    db: AsyncSession, attempt: MissionAttempt, mission: Mission, payload: MissionAttemptSubmit
) -> MissionAttempt:
    """Branches on `mission.workspace_type` — the one place that decides
    which deterministic grader applies, so every other caller (the
    endpoint, the frontend) only has to know "submit this attempt,"
    never which grading rules a specific Mission happens to use."""
    if mission.workspace_type == "investigation":
        return await _submit_investigation(db, attempt, mission, payload)
    if mission.workspace_type == "quiz":
        return await _submit_quiz(db, attempt, mission, payload)
    return await _submit_reflection(db, attempt, mission, payload)


async def _mark_completed_and_grant_evidence(
    db: AsyncSession, attempt: MissionAttempt, new_evidence
) -> None:
    assignment = await mission_service.get_assignment_for_employee_mission(
        db, attempt.mission_id, attempt.employee_id
    )
    if assignment and assignment.status != "completed":
        await mission_service.update_assignment_status(db, assignment, "completed")
    await capability_aggregation.recompute_profiles_for_evidence(db, attempt.employee_id, new_evidence)


async def _submit_investigation(
    db: AsyncSession, attempt: MissionAttempt, mission: Mission, payload: MissionAttemptSubmit
) -> MissionAttempt:
    evidence_viewed = _merge_evidence(attempt.evidence_viewed, payload.evidence_viewed)

    result = mission_scenarios.grade(
        mission.title, payload.affected_service or "", payload.likely_cause or "", evidence_viewed
    )

    attempt.affected_service = payload.affected_service
    attempt.likely_cause = payload.likely_cause
    attempt.reasoning = payload.reasoning
    attempt.evidence_viewed = evidence_viewed
    attempt.score = result.score
    attempt.passed = result.passed
    attempt.feedback = result.feedback
    attempt.status = "completed" if result.passed else "submitted"
    if result.passed:
        attempt.completed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(attempt)

    if result.passed:
        # Phase 3A: a genuinely completed mission is the only trigger for
        # capability evidence — a failed/incomplete attempt must never
        # fabricate positive evidence (see capability_evidence_pipeline.py).
        new_evidence = await capability_evidence_pipeline.extract_deterministic_evidence(db, attempt, result)
        await _mark_completed_and_grant_evidence(db, attempt, new_evidence)

    return attempt


async def _submit_quiz(
    db: AsyncSession, attempt: MissionAttempt, mission: Mission, payload: MissionAttemptSubmit
) -> MissionAttempt:
    answers = payload.quiz_answers or {}
    result = mission_quizzes.grade(mission.title, answers)

    attempt.quiz_answers = answers
    attempt.score = result.score
    attempt.passed = result.passed
    attempt.feedback = result.feedback
    attempt.status = "completed" if result.passed else "submitted"
    if result.passed:
        attempt.completed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(attempt)

    if result.passed:
        # No AI step for quiz missions — see mission.py's `workspace_type`
        # docstring: a multiple-choice pass/fail has nothing left for a
        # qualitative reader to add.
        new_evidence = await capability_evidence_pipeline.extract_quiz_evidence(db, attempt, result)
        await _mark_completed_and_grant_evidence(db, attempt, new_evidence)

    return attempt


async def _submit_reflection(
    db: AsyncSession, attempt: MissionAttempt, mission: Mission, payload: MissionAttemptSubmit
) -> MissionAttempt:
    score, passed, feedback = _grade_reflection(payload.reasoning)

    attempt.reasoning = payload.reasoning
    attempt.score = score
    attempt.passed = passed
    attempt.feedback = feedback
    attempt.status = "completed" if passed else "submitted"
    if passed:
        attempt.completed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(attempt)

    if passed:
        # The deterministic half of the two-stage pattern investigation
        # missions use — the AI's qualitative read on the same
        # `reasoning` text runs separately, once the frontend calls
        # POST /mission-attempts/{id}/evaluate on a completed attempt
        # (ai_evaluation_service.evaluate_attempt), never from here.
        new_evidence = await capability_evidence_pipeline.extract_reflection_evidence(db, attempt)
        await _mark_completed_and_grant_evidence(db, attempt, new_evidence)

    return attempt

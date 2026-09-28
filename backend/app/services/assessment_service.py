from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Assessment
from app.schemas.assessment import AssessmentSubmit
from app.services.assessment_questions import grade


async def get_by_session(db: AsyncSession, onboarding_session_id: str) -> Assessment | None:
    result = await db.execute(
        select(Assessment).where(Assessment.onboarding_session_id == onboarding_session_id)
    )
    return result.scalars().first()


async def submit_assessment(db: AsyncSession, payload: AssessmentSubmit) -> Assessment:
    answers = {a.question_id: a.selected_option for a in payload.answers}
    score, passed = grade(answers)

    assessment = await get_by_session(db, payload.onboarding_session_id)
    if assessment is None:
        assessment = Assessment(
            onboarding_session_id=payload.onboarding_session_id,
            employee_id=payload.employee_id,
        )
        db.add(assessment)

    assessment.answers = answers
    assessment.score = score
    assessment.passed = passed
    assessment.submitted_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(assessment)
    return assessment

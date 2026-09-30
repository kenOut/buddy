"""Phase A — Team Entity & Department -> Team Foundation. Minimal
list/create only, per the Team Architecture Impact Audit's own
recommendation — no update/delete yet, mirroring how
department_service.py itself has no update/delete either.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Team
from app.schemas.team import TeamCreate


class DuplicateTeamError(Exception):
    """Raised when a department already has a Team with this name —
    mirrors DuplicateWorkspaceIntegrationError's role: a genuine client
    error, not something to silently resolve."""


async def list_teams_for_department(db: AsyncSession, department_id: str) -> list[Team]:
    stmt = select(Team).where(Team.department_id == department_id).order_by(Team.name)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_team(db: AsyncSession, department_id: str, payload: TeamCreate) -> Team:
    team = Team(department_id=department_id, name=payload.name, description=payload.description)
    db.add(team)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateTeamError(
            f"Department {department_id} already has a team named {payload.name!r}"
        ) from exc
    await db.refresh(team)
    return team

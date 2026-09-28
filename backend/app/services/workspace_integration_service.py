"""Manager-facing WorkspaceIntegration configuration CRUD — Phase 8G.

Deliberately a separate module from workspace_access_service.py: that
module owns the *grant* lifecycle (who has access, triggered by
readiness); this one owns *configuration* (which workspace a department
even has). Configuration changes here never touch WorkspaceAccessGrant
— editing/deactivating/reactivating an integration leaves every existing
grant exactly as it was. Whether access gets (re-)granted remains
entirely governed by ReadinessService the next time a Quest completes;
nothing in this module calls ensure_access or any part of that chain.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WorkspaceIntegration
from app.schemas.workspace_integration import WorkspaceIntegrationCreate, WorkspaceIntegrationUpdate


class DuplicateWorkspaceIntegrationError(Exception):
    """Raised when a department already has a WorkspaceIntegration and
    a second is attempted — mirrors DuplicateQuestAssignmentError's
    role: a genuine client error (use PATCH to edit the existing one),
    not something to silently resolve."""


async def get_integration_for_department(
    db: AsyncSession, department_id: str
) -> WorkspaceIntegration | None:
    stmt = select(WorkspaceIntegration).where(WorkspaceIntegration.department_id == department_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_integration(
    db: AsyncSession, department_id: str, payload: WorkspaceIntegrationCreate
) -> WorkspaceIntegration:
    integration = WorkspaceIntegration(department_id=department_id, **payload.model_dump())
    db.add(integration)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateWorkspaceIntegrationError(
            f"Department {department_id} already has a workspace integration configured"
        ) from exc
    await db.refresh(integration)
    return integration


async def update_integration(
    db: AsyncSession, integration: WorkspaceIntegration, payload: WorkspaceIntegrationUpdate
) -> WorkspaceIntegration:
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(integration, field, value)
    await db.commit()
    await db.refresh(integration)
    return integration

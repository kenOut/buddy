from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.department import DepartmentCreate, DepartmentRead
from app.schemas.workspace_integration import (
    WorkspaceIntegrationCreate,
    WorkspaceIntegrationRead,
    WorkspaceIntegrationUpdate,
)
from app.services import department_service, workspace_integration_service
from app.services.workspace_integration_service import DuplicateWorkspaceIntegrationError

router = APIRouter(prefix="/departments", tags=["departments"])


@router.get("", response_model=list[DepartmentRead])
async def list_departments(organization_id: str | None = None, db: AsyncSession = Depends(get_db)):
    return await department_service.list_departments(db, organization_id)


@router.get("/{department_id}", response_model=DepartmentRead)
async def get_department(department_id: str, db: AsyncSession = Depends(get_db)):
    department = await department_service.get_department(db, department_id)
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    return department


@router.post("", response_model=DepartmentRead, status_code=201)
async def create_department(payload: DepartmentCreate, db: AsyncSession = Depends(get_db)):
    return await department_service.create_department(db, payload)


async def _get_owned_department(db: AsyncSession, department_id: str):
    department = await department_service.get_department(db, department_id)
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    return department


@router.get("/{department_id}/workspace", response_model=WorkspaceIntegrationRead | None)
async def get_department_workspace(department_id: str, db: AsyncSession = Depends(get_db)):
    """Returns null (not 404) when the department has no workspace
    configured yet — "not configured" is an ordinary, expected state
    for a department, not an error (same reasoning as GET .../evaluation
    returning CapabilityEvaluationRead | None elsewhere in this API)."""
    await _get_owned_department(db, department_id)
    return await workspace_integration_service.get_integration_for_department(db, department_id)


@router.post("/{department_id}/workspace", response_model=WorkspaceIntegrationRead, status_code=201)
async def create_department_workspace(
    department_id: str, payload: WorkspaceIntegrationCreate, db: AsyncSession = Depends(get_db)
):
    await _get_owned_department(db, department_id)
    try:
        return await workspace_integration_service.create_integration(db, department_id, payload)
    except DuplicateWorkspaceIntegrationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/{department_id}/workspace", response_model=WorkspaceIntegrationRead)
async def update_department_workspace(
    department_id: str, payload: WorkspaceIntegrationUpdate, db: AsyncSession = Depends(get_db)
):
    await _get_owned_department(db, department_id)
    integration = await workspace_integration_service.get_integration_for_department(db, department_id)
    if integration is None:
        raise HTTPException(
            status_code=404, detail="This department has no workspace configured yet — create one first"
        )
    return await workspace_integration_service.update_integration(db, integration, payload)

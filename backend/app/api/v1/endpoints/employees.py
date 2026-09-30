from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeDepartmentUpdate,
    EmployeeRead,
    EmployeeStatusUpdate,
)
from app.schemas.manager_performance import ManagerEmployeePerformanceResponse
from app.schemas.mission import MissionAssignmentRead
from app.schemas.provisioning import ProvisioningRequest
from app.services import (
    department_service,
    employee_service,
    manager_performance_service,
    mission_service,
    provisioning_service,
)
from app.services.provisioning_service import ProvisioningConflictError, UnknownReferenceError

router = APIRouter(prefix="/employees", tags=["employees"])

# Static, non-user-controlled directory (app/static/avatars, mounted at
# /static/avatars in main.py) — the employee_id + a content-type-derived
# extension is the only thing that ever becomes a filename, so nothing
# from the client's own filename ever reaches the filesystem.
_AVATAR_DIR = Path(__file__).resolve().parents[4] / "app" / "static" / "avatars"
_ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5MB


@router.get("", response_model=list[EmployeeRead])
async def list_employees(department_id: str | None = None, db: AsyncSession = Depends(get_db)):
    return await employee_service.list_employees(db, department_id)


@router.get("/{employee_id}", response_model=EmployeeRead)
async def get_employee(employee_id: str, db: AsyncSession = Depends(get_db)):
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return employee


@router.post("", response_model=EmployeeRead, status_code=201)
async def create_employee(payload: EmployeeCreate, db: AsyncSession = Depends(get_db)):
    """P2 — Provisioning Boundary. Routes through the same
    ProvisioningService any future HR/IdP integration will use — there
    is exactly one implementation of "create/resolve an employee, ensure
    their onboarding session, issue an invitation", not a separate one
    for the admin portal. The admin-facing request/response contract
    (EmployeeCreate in, EmployeeRead out, 201) is unchanged; only what
    happens underneath it changed. Note the behavioral upgrade this
    brings for free: an admin-created employee now also gets an eager
    OnboardingSession and an invitation, exactly like a provisioned one
    would — previously neither existed until the employee's first bundle
    fetch."""
    request = ProvisioningRequest(
        organization_id=payload.organization_id,
        identity_provider=payload.identity_provider,
        external_subject=payload.external_subject,
        email=payload.email,
        full_name=payload.full_name,
        department_id=payload.department_id,
        role_id=payload.role_id,
        manager_id=payload.manager_id,
        supervisor_id=payload.supervisor_id,
        team=payload.team,
        job_title=payload.job_title,
        employment_type=payload.employment_type,
        start_date=payload.start_date,
        status=payload.status,
    )
    try:
        result = await provisioning_service.provision_employee(db, request)
    except UnknownReferenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProvisioningConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return result.employee


@router.patch("/{employee_id}/status", response_model=EmployeeRead)
async def update_employee_status(
    employee_id: str, payload: EmployeeStatusUpdate, db: AsyncSession = Depends(get_db)
):
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return await employee_service.update_employee_status(db, employee, payload.status)


@router.patch("/{employee_id}/department", response_model=EmployeeRead)
async def update_employee_department(
    employee_id: str, payload: EmployeeDepartmentUpdate, db: AsyncSession = Depends(get_db)
):
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    if payload.department_id is not None:
        department = await department_service.get_department(db, payload.department_id)
        if department is None:
            raise HTTPException(status_code=404, detail="Department not found")

    return await employee_service.update_employee_department(db, employee, payload.department_id)


@router.post("/{employee_id}/avatar", response_model=EmployeeRead)
async def upload_employee_avatar(
    employee_id: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)
):
    """Admin-only in practice (no employee-facing client calls this — same
    trust level as create_employee/update_employee_department above,
    neither of which have an auth check of their own). Saves under a
    filename derived only from `employee_id` and the validated content
    type, never from the client's own filename."""
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    extension = _ALLOWED_CONTENT_TYPES.get(file.content_type or "")
    if extension is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported image type: {file.content_type!r}. Use JPEG, PNG, WebP, or GIF.",
        )

    contents = await file.read()
    if len(contents) > _MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="Image must be 5MB or smaller.")

    _AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    # Clear any previous avatar for this employee under a different
    # extension first, so switching file types can't leave an orphaned
    # (and now-unreferenced) file behind.
    for existing in _AVATAR_DIR.glob(f"{employee_id}.*"):
        existing.unlink(missing_ok=True)

    destination = _AVATAR_DIR / f"{employee_id}{extension}"
    destination.write_bytes(contents)

    return await employee_service.update_employee_avatar(
        db, employee, f"/static/avatars/{employee_id}{extension}"
    )


@router.get("/{employee_id}/missions", response_model=list[MissionAssignmentRead])
async def get_employee_missions(employee_id: str, db: AsyncSession = Depends(get_db)):
    assignments = await mission_service.list_assignments_for_employee(db, employee_id)
    return assignments


@router.get("/{employee_id}/performance", response_model=ManagerEmployeePerformanceResponse)
async def get_employee_performance(employee_id: str, db: AsyncSession = Depends(get_db)):
    """Manager Performance & Readiness Visibility — Stage 1. Admin-only
    (this whole router is registered with require_admin_session as a
    router-level dependency in api/v1/router.py — the same boundary
    /{employee_id}/missions above already uses), deliberately NOT the
    employee-session mechanism capabilities.py's endpoints use — see
    manager_performance_service's own module docstring for why that
    distinction matters for this specific endpoint."""
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return await manager_performance_service.get_employee_performance(db, employee)

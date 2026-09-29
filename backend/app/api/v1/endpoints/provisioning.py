from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.provisioning_auth import require_provisioning_credential
from app.schemas.provisioning import ProvisioningRequest, ProvisioningResult
from app.services import provisioning_service
from app.services.provisioning_service import ProvisioningConflictError, UnknownReferenceError

router = APIRouter(prefix="/provisioning", tags=["provisioning"])


@router.post(
    "/employees",
    response_model=ProvisioningResult,
    dependencies=[Depends(require_provisioning_credential)],
)
async def provision_employee(payload: ProvisioningRequest, db: AsyncSession = Depends(get_db)):
    """The service-to-service employee lifecycle entry point (see
    provisioning_service's module docstring). Gated by a provisioning
    credential — never the admin cookie, never an employee session (see
    core/provisioning_auth.py). Returns only enough for an internal
    caller to know what happened; never a raw invitation token, employee
    session, or bundle data (see ProvisioningResult's own docstring)."""
    try:
        result = await provisioning_service.provision_employee(db, payload)
    except UnknownReferenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProvisioningConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return ProvisioningResult(
        employee_id=result.employee.id,
        created=result.created,
        updated=result.updated,
        onboarding_session_created=result.onboarding_session_created,
        invitation_created=result.invitation_created,
        email_sent=result.email_sent,
        email_provider_ref=result.email_provider_ref,
    )

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.admin_auth import require_admin_session
from app.core.config import get_settings
from app.core.employee_auth import EMPLOYEE_SESSION_COOKIE_NAME, create_employee_session_token
from app.schemas.employee_invitation import (
    InvitationExchangeRequest,
    InvitationExchangeResponse,
    InvitationIssueResponse,
    InvitationResendResponse,
)
from app.services import email_service, employee_service, invitation_service
from app.services.invitation_service import InvitationError

router = APIRouter(prefix="/invitations", tags=["invitations"])


@router.post(
    "/employees/{employee_id}/issue",
    response_model=InvitationIssueResponse,
    dependencies=[Depends(require_admin_session)],
)
async def issue_invitation(employee_id: str, db: AsyncSession = Depends(get_db)):
    """Manager-portal-only — a development/test tool for retrieving a
    real, exchangeable raw token directly (Section 13 of the P3 brief:
    provisioning itself never returns one). Never exposed to the
    employee-facing surface, and deliberately does NOT send an email —
    for the real "get this employee a fresh invitation, delivered by
    email" action, see /resend below."""
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    invitation, raw_token = await invitation_service.issue_invitation(db, employee.id)
    return InvitationIssueResponse(
        id=invitation.id,
        employee_id=invitation.employee_id,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        token=raw_token,
    )


@router.post(
    "/employees/{employee_id}/resend",
    response_model=InvitationResendResponse,
    dependencies=[Depends(require_admin_session)],
)
async def resend_invitation(employee_id: str, db: AsyncSession = Depends(get_db)):
    """P3 — Email Provider Foundation (Section 14). The real,
    admin-gated recovery path when a provisioning-triggered welcome
    email failed to send, or an employee simply needs a fresh one: a
    new invitation is issued (through the same invitation_service.
    issue_invitation used everywhere else — no second token
    implementation), which revokes any still-active previous one as
    invitation_service already does, and the welcome email is sent
    for it through the same email_service used by provisioning.
    Never returns the raw token — unlike /issue above, this is the
    production-shaped action; the email is how the token reaches the
    employee."""
    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Captured before issue_invitation runs, not after — its own retry
    # loop can roll back internally on a losing race, which expires
    # every ORM object already attached to this session, `employee`
    # included. Same hazard, same fix, as provisioning_service.
    # provision_employee — see that module's docstring.
    employee_email = employee.email
    employee_full_name = employee.full_name

    _invitation, raw_token = await invitation_service.issue_invitation(db, employee_id)
    outcome = await email_service.send_welcome_invitation_email(
        employee_id=employee_id,
        employee_email=employee_email,
        employee_full_name=employee_full_name,
        raw_token=raw_token,
    )
    return InvitationResendResponse(sent=outcome.sent, provider_ref=outcome.provider_ref)


@router.post("/exchange", response_model=InvitationExchangeResponse)
async def exchange_invitation(
    payload: InvitationExchangeRequest, response: Response, db: AsyncSession = Depends(get_db)
):
    """The employee-facing entry point — deliberately unauthenticated,
    since there is no session yet at this point. See
    invitation_service.exchange_invitation for why every failure mode
    (unknown/expired/revoked/already-used) surfaces the same 401 status
    with only a machine-readable `reason` distinguishing them."""
    try:
        employee = await invitation_service.exchange_invitation(db, payload.token)
    except InvitationError as exc:
        raise HTTPException(status_code=401, detail={"reason": exc.reason})

    settings = get_settings()
    response.set_cookie(
        key=EMPLOYEE_SESSION_COOKIE_NAME,
        value=create_employee_session_token(employee.id),
        max_age=settings.employee_session_ttl_seconds,
        httponly=True,
        samesite="lax",
        # P5 — Production Security Hardening. Environment-aware, not
        # hardcoded — same reasoning as admin.py's admin_login cookie.
        secure=settings.environment == "production",
    )
    return InvitationExchangeResponse()

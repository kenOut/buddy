from datetime import datetime

from app.schemas.common import ORMBase


class InvitationExchangeRequest(ORMBase):
    token: str


class InvitationExchangeResponse(ORMBase):
    """Deliberately minimal — the employee session cookie set alongside
    this response is what actually authenticates subsequent requests;
    the frontend never needs employee data from this call itself."""

    authenticated: bool = True


class InvitationIssueResponse(ORMBase):
    """Manager-portal-only for this phase (see the /invitations/issue
    endpoint). `token` is the one and only place the raw invitation
    token is ever returned — it is never persisted and never appears in
    any other response."""

    id: str
    employee_id: str
    expires_at: datetime
    created_at: datetime
    token: str


class InvitationResendResponse(ORMBase):
    """P3 — Email Provider Foundation. Deliberately does NOT include
    `token`, unlike InvitationIssueResponse above — resend is the real,
    production-shaped "send this employee a fresh invitation email"
    action (see /invitations/employees/{id}/resend), not a dev/test
    tool for retrieving a raw token, so the token never leaves the
    server here at all; the email is how it reaches the employee."""

    sent: bool
    provider_ref: str | None = None

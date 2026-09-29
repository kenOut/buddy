from datetime import date

from pydantic import BaseModel

from app.schemas.common import ORMBase


class ProvisioningRequest(ORMBase):
    """The full current-state record for one employee, as the identity
    source (an HR/IdP system, or the admin portal on its behalf — see
    provisioning_service module docstring) understands it right now.

    Deliberately does not include `avatar_url`: that is a Buddy-native
    customization (see employees.py's dedicated upload endpoint), never
    an attribute an identity source would have an opinion about.

    Every provisioning call is treated as the authoritative full state
    for an already-resolved employee, not a sparse patch — omitting
    `department_id` on a later call means "this employee currently has
    no department", not "leave whatever was there before". This mirrors
    how upstream identity/HR sync APIs conventionally behave (e.g. SCIM)
    and keeps the update semantics unambiguous.
    """

    organization_id: str

    # Stable external identity (see provisioning_service's own
    # docstring). Both absent is a legitimate, common case — e.g. the
    # admin portal provisioning an employee with no external identity
    # provider — and always resolves to a brand-new employee, never an
    # existing one.
    identity_provider: str | None = None
    external_subject: str | None = None

    email: str
    full_name: str

    department_id: str | None = None
    role_id: str | None = None
    manager_id: str | None = None
    supervisor_id: str | None = None
    team: str | None = None
    job_title: str | None = None
    employment_type: str | None = None
    start_date: date | None = None

    # Only applied when a NEW employee is created. Never modified on an
    # update — see provisioning_service._apply_update's docstring for
    # why an identity re-sync must not be able to silently revert an
    # employee's own onboarding-status progress.
    status: str | None = None


class ProvisioningResult(BaseModel):
    """Deliberately minimal: enough for an internal provisioning caller
    to know what happened, nothing an employee-facing surface or a
    credential ever belongs in. No token hash, no employee session
    cookie, no capability/workspace/bundle data — see
    provisioning_service and the P1 invitation-issuance endpoint for why
    a raw invitation token is never returned from here.

    `email_sent`/`email_provider_ref` (P3 — Email Provider Foundation):
    provider-neutral, opaque, safe to expose to a provisioning caller —
    never a raw token, provider credential, or internal provider
    response payload (see email_provider.EmailSendResult's own
    docstring for that boundary). Both stay False/None whenever
    `invitation_created` is False — provisioning never attempts to send
    for a reused or already-used invitation."""

    employee_id: str
    created: bool
    updated: bool
    onboarding_session_created: bool
    invitation_created: bool
    email_sent: bool = False
    email_provider_ref: str | None = None

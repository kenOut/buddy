"""Provisioning boundary — the single, service-to-service entry point
for bringing an employee's identity into Buddy and preparing their
onboarding entry. Both the admin portal's employee-creation endpoint
(employees.py) and any future HR/IdP integration call through here
rather than each reimplementing employee upsert + eager
onboarding-session creation + invitation issuance separately. There is
exactly one implementation of this workflow.

Identity: `(identity_provider, external_subject)` is the stable
idempotency key (see app/models/employee.py) — never email, which is a
mutable contact attribute. An employee provisioned with no external
identity (both fields absent — today's overwhelming majority, since the
admin portal doesn't collect one) always creates a new row: there is no
meaningful way to "resolve" a null identity to an existing employee, and
none is attempted.

Email (the field): a contact attribute like any other organizational
field, updated once an employee is matched by their stable external
identity, subject to the same uniqueness constraint it always had —
never the idempotency key (see Identity above).

Email (the delivery, P3 — Email Provider Foundation): the welcome
invitation email is sent through the existing email_service, exactly
once, only when THIS call is the one that actually issues a brand-new
invitation (see the invitation_created branch below) — never for a
reused active invitation, and never for an employee who has already
completed a real exchange. A failed send never rolls back the
employee/session/invitation rows already committed; see
email_service.send_welcome_invitation_email's own docstring for the
full failure-handling story, and the P3 report's Resend section for
how a failed send is actually recovered from (an explicit,
admin-gated resend — not an automatic retry from repeated
provisioning).

Onboarding session: created eagerly, during provisioning, by calling
the existing `onboarding_service.get_or_create_session` — the same
function GET /onboarding/bundle/* already used to create sessions
lazily. Reusing it (rather than a second implementation) is what keeps
"GET bundle is read-only" true in the common case: by the time a
provisioned employee's bundle is ever fetched, their session already
exists, so that function's create-branch simply never fires for them.

Invitation: created through the existing `invitation_service`, never a
second token implementation. Repeated provisioning reuses a still-valid
active invitation rather than manufacturing a new one every call (see
`invitation_service.get_reusable_invitation`); an employee who has
already completed a real exchange is left alone entirely (see
`invitation_service.has_ever_used_invitation`) rather than having a new,
meaningless invitation issued after they're already in.

Authentication: this module has no opinion about who is allowed to call
it — that is app/core/provisioning_auth.py's job, a distinct service
credential, never the admin cookie or an employee session cookie.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee
from app.schemas.provisioning import ProvisioningRequest
from app.services import (
    department_service,
    email_service,
    employee_service,
    invitation_service,
    onboarding_service,
    organization_service,
    role_service,
)


class ProvisioningConflictError(Exception):
    """A provisioning request's data collides with a *different*
    employee than the one its external identity (if any) resolves to —
    e.g. the email already belongs to someone else. A genuine domain
    conflict (Section 9, Case B), not a race to be retried."""


class UnknownReferenceError(Exception):
    """organization_id/department_id/role_id/manager_id/supervisor_id
    doesn't resolve to an existing row. This project's SQLite setup runs
    with no foreign-key enforcement (see app/db/session.py — no PRAGMA
    foreign_keys), so without this explicit check the database would
    silently accept an orphaned reference rather than reject it."""

    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(message)


@dataclass
class ProvisioningResult:
    employee: Employee
    created: bool
    updated: bool
    onboarding_session_created: bool
    invitation_created: bool
    # P3 — Email Provider Foundation. Only meaningful when
    # invitation_created is True — provisioning never re-sends for a
    # reused/already-used invitation (Section 11), so these stay
    # False/None on every call that didn't just create a brand-new one.
    email_sent: bool = False
    email_provider_ref: str | None = None


async def _get_employee_by_external_identity(
    db: AsyncSession, identity_provider: str, external_subject: str
) -> Employee | None:
    result = await db.execute(
        select(Employee)
        .where(Employee.identity_provider == identity_provider)
        .where(Employee.external_subject == external_subject)
    )
    return result.scalars().first()


async def _validate_references(db: AsyncSession, request: ProvisioningRequest) -> None:
    if await organization_service.get_organization(db, request.organization_id) is None:
        raise UnknownReferenceError("organization_id", "Unknown organization_id.")
    if request.department_id is not None:
        if await department_service.get_department(db, request.department_id) is None:
            raise UnknownReferenceError("department_id", "Unknown department_id.")
    if request.role_id is not None:
        if await role_service.get_role(db, request.role_id) is None:
            raise UnknownReferenceError("role_id", "Unknown role_id.")
    if request.manager_id is not None:
        if await employee_service.get_employee(db, request.manager_id) is None:
            raise UnknownReferenceError("manager_id", "Unknown manager_id.")
    if request.supervisor_id is not None:
        if await employee_service.get_employee(db, request.supervisor_id) is None:
            raise UnknownReferenceError("supervisor_id", "Unknown supervisor_id.")


def _apply_organizational_fields(employee: Employee, request: ProvisioningRequest) -> None:
    """Shared by both the create and update paths so the two can never
    silently drift apart on which fields a provisioning request
    controls. `status` is deliberately NOT here — see
    `_update_existing`'s docstring."""
    employee.organization_id = request.organization_id
    employee.department_id = request.department_id
    employee.role_id = request.role_id
    employee.manager_id = request.manager_id
    employee.supervisor_id = request.supervisor_id
    employee.full_name = request.full_name
    employee.email = request.email
    employee.job_title = request.job_title
    employee.team = request.team
    if request.employment_type is not None:
        employee.employment_type = request.employment_type
    employee.start_date = request.start_date
    employee.identity_provider = request.identity_provider
    employee.external_subject = request.external_subject


async def _update_existing(db: AsyncSession, employee: Employee, request: ProvisioningRequest) -> Employee:
    """Updates an employee already resolved by external identity.
    `status` is intentionally never touched here: Buddy's own onboarding
    flow owns status transitions (PATCH /employees/{id}/status) —  an
    identity-source re-sync must not be able to silently revert an
    employee's own progress back to e.g. "invited"."""
    _apply_organizational_fields(employee, request)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ProvisioningConflictError(
            "Updating this employee would collide with a different existing employee "
            "(most likely: this email already belongs to someone else)."
        ) from exc
    await db.refresh(employee)
    return employee


async def _create_or_recover(
    db: AsyncSession, request: ProvisioningRequest, has_identity: bool
) -> tuple[Employee, bool]:
    """Attempts to create a new employee. On a uniqueness conflict,
    checks whether the conflict was actually a concurrent caller
    creating the *same* external identity (a race to recover from, not a
    real conflict) before giving up as a genuine ProvisioningConflictError.
    See the module's Concurrency notes in the P2 final report."""
    employee = Employee(status=request.status or "invited")
    _apply_organizational_fields(employee, request)
    db.add(employee)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        if has_identity:
            winner = await _get_employee_by_external_identity(
                db, request.identity_provider, request.external_subject
            )
            if winner is not None:
                updated = await _update_existing(db, winner, request)
                return updated, False
        raise ProvisioningConflictError(
            "An employee with this email, or this external identity, already exists."
        )
    await db.refresh(employee)
    return employee, True


async def provision_employee(db: AsyncSession, request: ProvisioningRequest) -> ProvisioningResult:
    await _validate_references(db, request)

    has_identity = bool(request.identity_provider and request.external_subject)
    existing = None
    if has_identity:
        existing = await _get_employee_by_external_identity(
            db, request.identity_provider, request.external_subject
        )

    if existing is not None:
        employee = await _update_existing(db, existing, request)
        created = False
    else:
        employee, created = await _create_or_recover(db, request, has_identity)

    # Captured now, once, as plain strings — not read from `employee`
    # again below. get_or_create_session and issue_invitation each have
    # their own internal rollback-and-retry on a losing race, and a
    # rollback expires every ORM object already attached to this shared
    # `db` session, `employee` included, regardless of which function's
    # rollback it was. Re-reading `employee.<attr>` after that would
    # trigger an implicit lazy-load that async SQLAlchemy cannot safely
    # perform outside its own request-dispatch context (see
    # invitation_service.get_reusable_invitation's docstring for the
    # full explanation — this is the call site that made it necessary,
    # now extended to email/full_name for the same reason).
    employee_id = employee.id
    employee_email = employee.email
    employee_full_name = employee.full_name

    _session, session_created = await onboarding_service.get_or_create_session(db, employee)

    invitation_created = False
    email_sent = False
    email_provider_ref = None
    reusable = await invitation_service.get_reusable_invitation(db, employee_id)
    if reusable is None and not await invitation_service.has_ever_used_invitation(db, employee_id):
        _invitation, raw_token = await invitation_service.issue_invitation(db, employee_id)
        invitation_created = True

        # P3 — Email Provider Foundation. Sent exactly once, only for a
        # genuinely new invitation (Section 11) — reusing an existing
        # active one, or leaving an already-entered employee alone,
        # both skip this entirely, above. `raw_token` goes out of scope
        # the moment this call returns; nothing here stores, logs, or
        # returns it (see email_service.send_welcome_invitation_email's
        # own docstring). A failed send does not roll back anything
        # committed above — see that function's docstring for why.
        outcome = await email_service.send_welcome_invitation_email(
            employee_id=employee_id,
            employee_email=employee_email,
            employee_full_name=employee_full_name,
            raw_token=raw_token,
        )
        email_sent = outcome.sent
        email_provider_ref = outcome.provider_ref

    # A belt-and-suspenders refresh: guarantees the `employee` object
    # handed back to the caller (the admin endpoint serializes it
    # directly as EmployeeRead) is never stale, even though nothing
    # above should have expired it now that employee_id/email/full_name
    # are what's actually threaded through the calls that can roll back.
    await db.refresh(employee)

    return ProvisioningResult(
        employee=employee,
        created=created,
        updated=not created,
        onboarding_session_created=session_created,
        invitation_created=invitation_created,
        email_sent=email_sent,
        email_provider_ref=email_provider_ref,
    )

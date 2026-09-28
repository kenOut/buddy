"""Workspace access grant lifecycle — Phase 8C.

`ensure_access(db, employee_id, workspace_integration_id)` is the single
entry point. It answers "given an employee and a configured workspace,
can/should access be granted?" — it does NOT answer "has this employee
completed all requirements to be ready?" (that's ReadinessService,
Phase 8D, and does not exist yet). Nothing in this module is called from
anywhere yet; there is no trigger wired into quest completion.

Deliberately has zero imports from the Quest evaluation chain
(quest_evaluation_service, quest_attempt_service, capability_*,
recommendation_*, development_journey) — this module only reads
Employee/WorkspaceIntegration and reads/writes WorkspaceAccessGrant.
That keeps the dependency direction strictly one-way:

    Quest system --(future trigger)--> WorkspaceAccessService

never the reverse. A provider failure here can therefore only ever
affect WorkspaceAccessGrant; there is no code path by which it could
reach back into QuestAttempt/OnboardingSession/CapabilityProfile/
Recommendation, because this module never imports, queries, or writes
any of them.

PENDING state (Phase 8C is synchronous, in-process — no background
worker exists in this project, see Phase 8A's inspection report): a
PENDING row can only mean one of two things when `ensure_access` sees
it — (1) it was just created by this same call, one line above, or (2)
a previous call crashed between creating the row and finishing the
provider round-trip. Either way, the only safe synchronous action is to
attempt the provider call now; there is nothing else that will ever pick
it up. This is why PENDING and FAILED share the same retry path below —
both mean "no successful grant exists yet; try the provider."

REVOKED is returned as-is, untouched. Re-provisioning after a revoke is
a deliberate policy decision (Phase 8C makes no attempt to guess at it),
not a mechanical retry like PENDING/FAILED.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Employee, WorkspaceAccessGrant, WorkspaceIntegration
from app.schemas.workspace_access import EmployeeWorkspaceAccess
from app.services.workspace_provider import WorkspaceProviderError, get_workspace_provider


class EmployeeNotFoundError(Exception):
    """Raised when ensure_access is called with an employee_id that
    doesn't exist. A caller error — never written to
    WorkspaceAccessGrant.last_error, which is reserved for provider
    failures against a real, existing grant."""


class WorkspaceIntegrationNotFoundError(Exception):
    """Raised when ensure_access is called with a workspace_integration_id
    that doesn't exist. Same caller-error class as EmployeeNotFoundError."""


async def _get_grant(
    db: AsyncSession, employee_id: str, workspace_integration_id: str, *, for_update: bool = False
) -> WorkspaceAccessGrant | None:
    """`for_update=True` adds `SELECT ... FOR UPDATE` (Phase 8F-3) — on
    Postgres, a second concurrent `ensure_access` call for the same
    (employee, workspace) blocks here until the first transaction's next
    commit releases the row lock, instead of both transactions reading
    the row at the same instant with no ordering between them at all.
    On SQLite (this project's dev/test database), `FOR UPDATE` compiles
    to nothing — confirmed by inspection, not assumed — so this is a
    real, honest no-op there, never a false sense of protection. See
    ensure_access's docstring for exactly what this does and does not
    guarantee even on Postgres."""
    stmt = select(WorkspaceAccessGrant).where(
        WorkspaceAccessGrant.employee_id == employee_id,
        WorkspaceAccessGrant.workspace_integration_id == workspace_integration_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _attempt_provider_grant(
    db: AsyncSession,
    employee: Employee,
    workspace: WorkspaceIntegration,
    grant: WorkspaceAccessGrant,
) -> WorkspaceAccessGrant:
    """The only place attempt_count is incremented and the only place a
    provider is ever called — exactly once per invocation. Marks the
    grant PENDING and commits before the (potentially slow/failable)
    provider call, same reasoning as quest_evaluation_service.evaluate_
    attempt marking EVALUATING before its own slow work: a crash here
    leaves an accurate, resumable state instead of a stale one.

    Only this function — never the provider — writes status/
    attempt_count/provider_ref/granted_at/last_error onto the grant.

    `result.provider_ref` is stored verbatim and never interpreted —
    this function contains no branch shaped like `if provider_ref.
    startswith(...)` and never will; see workspace_provider.py's module
    docstring for why. `result.workspace_link` is deliberately NOT
    persisted here (Phase 8F-1 formalization, not a new decision): the
    employee-facing link is, and remains, `WorkspaceIntegration.
    workspace_link` — the value a manager explicitly configured — so a
    provider can never silently override what a manager set. A
    provider's returned `workspace_link` exists in the contract for a
    provider that needs to report the effective link back (e.g. if a
    real provider generates or resolves one), but nothing downstream
    reads it today; get_employee_access() always serves the configured
    value. Changing that would be a deliberate future decision, not a
    side effect of adding a real provider.
    """
    grant.attempt_count += 1
    grant.status = "PENDING"
    await db.commit()
    await db.refresh(grant)

    settings = get_settings()
    try:
        provider = get_workspace_provider(settings.workspace_provider)
        result = await provider.grant_access(employee_email=employee.email, workspace=workspace)
    except WorkspaceProviderError as exc:
        # Covers both an unconfigured/unsupported provider selection and
        # (for a real provider, later) total unavailability — either way,
        # no exception escapes to the caller; it becomes a FAILED grant,
        # retryable exactly like any other provider failure.
        grant.status = "FAILED"
        grant.last_error = str(exc)
        await db.commit()
        await db.refresh(grant)
        return grant

    if result.success:
        grant.status = "GRANTED"
        grant.provider_ref = result.provider_ref
        grant.granted_at = grant.granted_at or datetime.now(timezone.utc)
        grant.last_error = None
    else:
        grant.status = "FAILED"
        grant.last_error = result.error or "Workspace provider reported failure with no further detail."

    await db.commit()
    await db.refresh(grant)
    return grant


async def ensure_access(
    db: AsyncSession, employee_id: str, workspace_integration_id: str
) -> WorkspaceAccessGrant:
    """Idempotent and concurrency-safe, mirroring quest_evaluation_
    service.evaluate_attempt's established pattern: already-GRANTED
    short-circuits with no provider call and no write; a fresh grant is
    created get-or-create style (IntegrityError from a concurrent caller
    creating the same row is caught and recovered from by re-fetching,
    never treated as an error); PENDING/FAILED both retry the provider
    exactly once per call.

    Concurrency guarantee (Phase 8F-3, exact and not overstated): the
    existing-grant fetch uses `SELECT ... FOR UPDATE` (via `_get_grant
    (..., for_update=True)`). On Postgres this serializes two concurrent
    `ensure_access` calls for the same (employee, workspace) against
    each other for the fetch itself — a second transaction blocks here
    until the first's next commit. Combined with the existing
    `UNIQUE(employee_id, workspace_integration_id)` constraint (which
    this function already handles via the IntegrityError-recovery
    above), this makes "at most one grant ROW ever exists" fully
    guaranteed on Postgres, not just on the happy path.

    What this does NOT guarantee, on Postgres or anywhere else: that the
    external provider is called at most once. `_attempt_provider_grant`
    commits the PENDING transition *before* calling the provider (so a
    crash mid-call leaves a resumable state, not a stale one) — that
    commit releases the row lock, so a second transaction that was
    blocked on the FOR UPDATE fetch can unblock, see status=PENDING, and
    still attempt the provider itself. Closing that fully would mean
    holding a database row lock for the entire duration of a slow,
    external HTTP call — a worse tradeoff than the race it would close,
    and not something this phase introduces. This is an accepted,
    documented limitation of the current synchronous, no-worker
    architecture (see Phase 8A's inspection report), not an oversight.
    """
    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise EmployeeNotFoundError(employee_id)

    workspace = await db.get(WorkspaceIntegration, workspace_integration_id)
    if workspace is None:
        raise WorkspaceIntegrationNotFoundError(workspace_integration_id)

    grant = await _get_grant(db, employee_id, workspace_integration_id, for_update=True)

    if grant is None:
        grant = WorkspaceAccessGrant(
            employee_id=employee_id,
            workspace_integration_id=workspace_integration_id,
            status="PENDING",
        )
        db.add(grant)
        try:
            await db.commit()
        except IntegrityError:
            # Lost a race with a concurrent ensure_access call for the
            # same (employee, workspace) — the unique constraint caught
            # it. Re-fetch (locked) the row the other call created
            # instead of raising; see this function's own docstring for
            # what the lock does and does not guarantee under true
            # concurrency.
            await db.rollback()
            grant = await _get_grant(db, employee_id, workspace_integration_id, for_update=True)
        else:
            await db.refresh(grant)

    if grant.status == "GRANTED":
        return grant  # idempotent no-op — no provider call, no write

    if grant.status == "REVOKED":
        return grant  # deliberately not auto-retried — see module docstring

    # PENDING or FAILED — both resolve the same way, see module docstring.
    return await _attempt_provider_grant(db, employee, workspace, grant)


async def _get_active_integration(db: AsyncSession, department_id: str) -> WorkspaceIntegration | None:
    stmt = select(WorkspaceIntegration).where(
        WorkspaceIntegration.department_id == department_id,
        WorkspaceIntegration.active.is_(True),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# DB WorkspaceAccessGrant.status -> API-safe EmployeeWorkspaceAccess.status.
# See schemas/workspace_access.py's WORKSPACE_ACCESS_API_STATUSES for why
# REVOKED maps to FAILED (unreachable today, kept only so this mapping is
# total) and why there is no DB counterpart for NOT_CONFIGURED.
_GRANT_STATUS_TO_API_STATUS = {
    "GRANTED": "GRANTED",
    "PENDING": "PENDING",
    "FAILED": "FAILED",
    "REVOKED": "FAILED",
}


async def get_employee_access(db: AsyncSession, employee: Employee) -> EmployeeWorkspaceAccess:
    """Phase 8E — a pure read, never a trigger. Reports only what
    WorkspaceIntegration/WorkspaceAccessGrant already say; never computes
    or leaks readiness (see the API-level status contract's docstring in
    schemas/workspace_access.py). Safe to call as often as the frontend
    likes — no writes, no provider calls, ever.
    """
    if employee.department_id is None:
        return EmployeeWorkspaceAccess(status="NOT_CONFIGURED", workspace_name=None, workspace_link=None)

    integration = await _get_active_integration(db, employee.department_id)
    if integration is None:
        return EmployeeWorkspaceAccess(status="NOT_CONFIGURED", workspace_name=None, workspace_link=None)

    grant = await _get_grant(db, employee.id, integration.id)
    if grant is None:
        return EmployeeWorkspaceAccess(
            status="NOT_CONFIGURED", workspace_name=integration.display_name, workspace_link=None
        )

    api_status = _GRANT_STATUS_TO_API_STATUS[grant.status]
    # Always the manager-configured link (WorkspaceIntegration.
    # workspace_link), never anything derived from grant.provider_ref —
    # see _attempt_provider_grant's docstring for why a provider's own
    # returned workspace_link is accepted into the contract but not
    # persisted or surfaced here today.
    return EmployeeWorkspaceAccess(
        status=api_status,
        workspace_name=integration.display_name,
        workspace_link=integration.workspace_link if api_status == "GRANTED" else None,
    )

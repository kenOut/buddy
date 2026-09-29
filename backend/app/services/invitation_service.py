"""Invitation lifecycle — issuing and exchanging a temporary credential
that grants an employee entry into onboarding (see
app/models/employee_invitation.py for why this is a distinct concept
from OnboardingSession).

Token hashing: the raw token is a 256-bit value from `secrets.token_urlsafe`
(stdlib, no new dependency) — cryptographically random, never a
human-chosen secret. That distinction is what governs the hashing
choice: a slow, salted KDF (bcrypt/scrypt/argon2) exists to make
brute-forcing a *low-entropy, guessable* secret expensive, which is not
the threat model here (a 256-bit random value is not brute-forceable
regardless of hash speed). What a stored hash needs to defend against
for a bearer token like this is a raw database leak being directly
replayable. HMAC-SHA256 keyed with a server-side secret
(`settings.invitation_token_secret`) does exactly that — a leaked
`token_hash` value is useless without also knowing the secret — while
staying fast and dependency-free, mirroring the exact pattern
admin_auth.py already uses for the Manager Portal session token.
"""

import hmac
import secrets
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Employee, EmployeeInvitation

# Bounds issue_invitation's internal retry-on-race loop (see its
# docstring). Generous relative to any realistic concurrent-caller count
# this app will see — not a tunable, just a sanity backstop against an
# infinite loop if something is structurally wrong.
_MAX_ISSUE_ATTEMPTS = 10


class InvitationError(Exception):
    """Base for every invitation-exchange failure. `reason` is a stable,
    machine-readable code the API layer forwards to the client for UX
    copy (Section 17's Expired/Revoked/Already-used/Invalid states) —
    always alongside the same generic HTTP status, so distinguishing
    *why* a token someone already possesses stopped working is not the
    same thing as letting a blind guesser learn whether a token or
    employee exists (see exchange_invitation's docstring)."""

    reason = "invalid"


class UnknownTokenError(InvitationError):
    reason = "invalid"


class ExpiredInvitationError(InvitationError):
    reason = "expired"


class RevokedInvitationError(InvitationError):
    reason = "revoked"


class UsedInvitationError(InvitationError):
    reason = "used"


def _hash_token(raw_token: str) -> str:
    settings = get_settings()
    return hmac.new(settings.invitation_token_secret.encode(), raw_token.encode(), sha256).hexdigest()


def _generate_raw_token() -> str:
    return secrets.token_urlsafe(32)


async def _get_active_invitation(db: AsyncSession, employee_id: str) -> EmployeeInvitation | None:
    """`used_at IS NULL AND revoked_at IS NULL` — deliberately not
    expiry-aware (see uq_employee_invitation_active's own comment for
    why): this is "the one row that currently occupies the active
    slot", not "a row someone could still successfully exchange". Use
    get_reusable_invitation for the latter."""
    result = await db.execute(
        select(EmployeeInvitation)
        .where(EmployeeInvitation.employee_id == employee_id)
        .where(EmployeeInvitation.used_at.is_(None))
        .where(EmployeeInvitation.revoked_at.is_(None))
    )
    return result.scalars().first()


async def get_reusable_invitation(db: AsyncSession, employee_id: str) -> EmployeeInvitation | None:
    """P2 — Provisioning Boundary. An invitation a caller could hand to
    the employee right now and have it actually work: active AND not yet
    expired. Distinct from `_get_active_invitation` above, which the
    exchange/issue race-handling paths use and which doesn't care about
    expiry — provisioning cares, because reusing an already-expired
    "active" row would silently hand out a token that fails on exchange.

    Takes a plain `employee_id`, not an `Employee` object, on purpose:
    provisioning_service may call this after an earlier step in the same
    request rolled back a retried write, which expires every ORM object
    already attached to that session (including an `Employee` the
    caller resolved earlier) — reading an expired attribute triggers an
    implicit lazy-load that async SQLAlchemy cannot safely perform
    outside its own request-dispatch context. Taking the id directly
    sidesteps that hazard structurally rather than requiring every
    caller to remember to re-refresh first."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(EmployeeInvitation)
        .where(EmployeeInvitation.employee_id == employee_id)
        .where(EmployeeInvitation.used_at.is_(None))
        .where(EmployeeInvitation.revoked_at.is_(None))
        .where(EmployeeInvitation.expires_at > now)
    )
    return result.scalars().first()


async def has_ever_used_invitation(db: AsyncSession, employee_id: str) -> bool:
    """P2 — Provisioning Boundary. True once this employee has completed
    a real invitation exchange at least once. Provisioning uses this to
    avoid resurrecting/reissuing an invitation for someone who is
    already authenticated and onboarding — re-provisioning an existing,
    already-entered employee should not manufacture a fresh "come join
    Buddy" credential for them. Takes `employee_id` directly — see
    get_reusable_invitation's docstring for why."""
    result = await db.execute(
        select(EmployeeInvitation.id)
        .where(EmployeeInvitation.employee_id == employee_id)
        .where(EmployeeInvitation.used_at.is_not(None))
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def issue_invitation(db: AsyncSession, employee_id: str) -> tuple[EmployeeInvitation, str]:
    """Issues a fresh invitation for the employee named by `employee_id`,
    revoking any existing still-active one first (at most one active
    invitation per employee — enforced here in service logic, and backed
    by uq_employee_invitation_active as a real database guarantee
    against a race between two concurrent issue calls). Historical
    (used/revoked) invitations are never deleted.

    Takes a plain `employee_id`, not an `Employee` object — see
    get_reusable_invitation's docstring for why (this function's own
    retry loop rolls back on a losing race, which is exactly the
    expired-attribute hazard that guards against).

    Returns the persisted invitation row alongside the raw token — the
    ONLY place the raw token is ever available; it is not stored and
    must not be logged by any caller.

    Race-safe under N concurrent callers (P2 — Provisioning Boundary):
    if two callers both see "no active invitation" and both try to
    insert the first one, the loser's commit raises IntegrityError
    against uq_employee_invitation_active. Rather than surface that to
    the caller, this retries — the next attempt re-reads state, finds
    the winner's now-active row, revokes it, and inserts its own, which
    cannot conflict with anything by construction. Bounded so a
    structural problem fails loudly instead of looping forever.
    """
    settings = get_settings()

    for _attempt in range(_MAX_ISSUE_ATTEMPTS):
        existing = await _get_active_invitation(db, employee_id)

        now = datetime.now(timezone.utc)
        if existing is not None:
            existing.revoked_at = now

        raw_token = _generate_raw_token()
        invitation = EmployeeInvitation(
            employee_id=employee_id,
            token_hash=_hash_token(raw_token),
            expires_at=now + timedelta(seconds=settings.invitation_ttl_seconds),
        )
        db.add(invitation)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            continue
        await db.refresh(invitation)
        return invitation, raw_token

    raise RuntimeError(
        f"Could not issue an invitation for employee {employee.id} after "
        f"{_MAX_ISSUE_ATTEMPTS} attempts — persistent contention or a "
        "structural constraint problem."
    )


async def exchange_invitation(db: AsyncSession, raw_token: str) -> Employee:
    """Validates and consumes a raw invitation token, returning the
    employee it belongs to.

    The actual consuming operation is a single conditional UPDATE
    (`used_at IS NULL AND revoked_at IS NULL AND expires_at > now`) —
    not a SELECT-then-check-then-UPDATE — so two concurrent requests
    racing the same valid token can both reach this function, but only
    one UPDATE statement will affect a row; the loser sees `rowcount ==
    0` and is rejected as "already used". This is a real guarantee
    backed by the database's own row-level write serialization, not an
    application-level lock claiming more than that.

    Every failure mode (unknown token, expired, revoked, already used)
    raises an InvitationError subclass; the API layer maps all of them
    to the same HTTP status so a caller blindly guessing tokens can't
    learn whether a given token — or the employee behind it — exists.
    The specific `reason` is only meaningful to a caller who already
    holds a real, once-valid token (e.g. clicking a stale email link),
    which is not the threat the generic status code protects against.
    """
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)

    result = await db.execute(
        update(EmployeeInvitation)
        .where(EmployeeInvitation.token_hash == token_hash)
        .where(EmployeeInvitation.used_at.is_(None))
        .where(EmployeeInvitation.revoked_at.is_(None))
        .where(EmployeeInvitation.expires_at > now)
        .values(used_at=now)
    )

    if result.rowcount != 1:
        await db.rollback()
        invitation = (
            await db.execute(
                select(EmployeeInvitation).where(EmployeeInvitation.token_hash == token_hash)
            )
        ).scalar_one_or_none()
        if invitation is None:
            raise UnknownTokenError()
        if invitation.revoked_at is not None:
            raise RevokedInvitationError()
        if invitation.used_at is not None:
            raise UsedInvitationError()
        raise ExpiredInvitationError()

    invitation = (
        await db.execute(select(EmployeeInvitation).where(EmployeeInvitation.token_hash == token_hash))
    ).scalar_one()
    employee = await db.get(Employee, invitation.employee_id)
    await db.commit()
    return employee

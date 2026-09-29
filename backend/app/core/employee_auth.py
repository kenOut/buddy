"""Employee-facing session — the credential an employee holds after a
successful, single-use invitation exchange (see
app/services/invitation_service.py). Deliberately mirrors
admin_auth.py's stateless, HMAC-signed cookie pattern rather than
inventing a second session mechanism: same token shape, same
constant-time verification, same "nothing to look up in storage"
property. Kept as a fully separate cookie/secret from the admin session
throughout, though — a leak of one credential type must never implicate
the other, and an employee session must never be usable to reach the
Manager Portal (or vice versa).

Token format (before base64url-encoding):
`{employee_id}.{expires_at}.{signature}`, where
`signature = HMAC-SHA256(secret, f"{employee_id}.{expires_at}")`.
"""

import base64
import hmac
import time
from hashlib import sha256

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.models import Employee

EMPLOYEE_SESSION_COOKIE_NAME = "buddy_employee_session"


def _sign(employee_id: str, expires_at: int) -> str:
    settings = get_settings()
    payload = f"{employee_id}.{expires_at}"
    return hmac.new(settings.employee_session_secret.encode(), payload.encode(), sha256).hexdigest()


def create_employee_session_token(employee_id: str) -> str:
    settings = get_settings()
    expires_at = int(time.time()) + settings.employee_session_ttl_seconds
    signature = _sign(employee_id, expires_at)
    raw = f"{employee_id}.{expires_at}.{signature}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def verify_employee_session_token(token: str | None) -> str | None:
    """Returns the employee_id the token was issued for, or None if the
    token is missing, malformed, expired, or fails signature
    verification."""
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        employee_id, expires_at_str, signature = raw.split(".", 2)
        expires_at = int(expires_at_str)
    except (ValueError, UnicodeDecodeError):
        return None

    if time.time() > expires_at:
        return None
    if not hmac.compare_digest(signature, _sign(employee_id, expires_at)):
        return None
    return employee_id


async def get_current_employee(
    buddy_employee_session: str | None = Cookie(default=None, alias=EMPLOYEE_SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> Employee:
    """FastAPI dependency — the only way an employee-facing route should
    resolve "which employee is asking" going forward. Never trusts a
    client-supplied employee_id from a path, query, or body param for
    identity; the session cookie is the sole source of truth, so a
    request can never override its own identity by passing a different
    id. A missing/tampered/expired session and a session naming an
    employee who no longer exists both raise the same 401 — the two
    cases must look identical to the caller."""
    employee_id = verify_employee_session_token(buddy_employee_session)
    if employee_id is None:
        raise HTTPException(status_code=401, detail="Sign-in required")

    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=401, detail="Sign-in required")

    return employee


async def require_employee_session(
    buddy_employee_session: str | None = Cookie(default=None, alias=EMPLOYEE_SESSION_COOKIE_NAME),
) -> str | None:
    """P5 — Production Security Hardening (as `get_optional_employee_
    session`) / P5.1 — Production Employee Authorization Hardening
    (made production-required). Companion to `get_current_employee` for
    the routes that predate it (mission_attempts.py, capabilities.py,
    quests.py's employee-facing endpoints, and onboarding.py's
    session/assessment routes) — every one of them still resolves
    "which employee" from a client-supplied `employee_id` (or an
    owning resource's own `employee_id`) rather than the session alone,
    by original design, so this app has two legitimate ways to reach
    them: fully unauthenticated demo mode (no cookie at all — see
    `/onboarding/bundle/demo`), and real invitation-exchanged sessions.
    Requiring `get_current_employee` outright on these routes would
    break demo mode entirely — which is exactly why this dependency
    exists instead of just using that one everywhere.

    Behavior is now environment-conditional:

      - `environment == "production"`: a missing/malformed/tampered/
        expired session now raises 401 — production has no legitimate
        unauthenticated caller for any of these routes (P4.1 already
        guarantees zero demo organizations/employees exist there, so
        there is no "demo mode" left to preserve). This closes the
        residual P5 gap: previously, in EVERY environment including
        production, a request with no session at all could still reach
        another employee's data by simply supplying their employee_id,
        because `assert_caller_is_employee` only checks a session that
        is actually present.
      - anything else (development/test): unchanged from P5 — returns
        the session's employee_id when a valid cookie is present, or
        None when there isn't one (missing, malformed, tampered, or
        expired all collapse to None here, exactly like
        `get_current_employee`'s own indistinguishable-401 reasoning),
        preserving the existing zero-auth demo/dev workflow exactly.

    Pair with `assert_caller_is_employee` at the call site, unchanged:
    in production this function's return value is never `None`, so
    that check now always enforces exact identity there — no change to
    `assert_caller_is_employee` itself was needed to close the gap.
    """
    settings = get_settings()
    employee_id = verify_employee_session_token(buddy_employee_session)
    if settings.environment == "production" and employee_id is None:
        raise HTTPException(status_code=401, detail="Sign-in required")
    return employee_id


def assert_caller_is_employee(requested_employee_id: str, session_employee_id: str | None) -> None:
    """Raises 403 only when a valid employee session IS present and
    names a different employee than the one the request targets. A
    None session_employee_id is deliberately not an error here by
    itself — see `require_employee_session` for why: outside
    production it means "no session, demo mode" (unchanged, allowed);
    in production `require_employee_session` never returns None at all
    (it raises 401 first), so this function's None-is-ok branch is
    already unreachable there in practice — production's enforcement
    comes from `require_employee_session` raising, not from this
    function rejecting a None."""
    if session_employee_id is not None and session_employee_id != requested_employee_id:
        raise HTTPException(status_code=403, detail="Not authorized for this employee")

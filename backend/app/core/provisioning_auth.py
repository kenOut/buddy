"""Provisioning credential — the auth boundary for
POST /provisioning/employees.

This is a THIRD, independent credential type in this app, never to be
confused with the other two:

    Employee              -> employee session cookie   (core/employee_auth.py)
    Manager (browser)     -> admin session cookie       (core/admin_auth.py)
    HR/IdP/service caller -> provisioning credential    (this file)

A browser admin session must never satisfy this dependency, and this
credential must never be accepted as proof of an employee or admin
session. There is no shared code between the three on purpose — each
protects a different kind of caller, and collapsing them would let a
compromise of one credential type reach the others' surface.

Sent as `Authorization: Bearer <provisioning-secret>` — a header, never
a query parameter (query strings end up in server logs, browser
history, and proxy access logs far more readily than headers). Compared
with `hmac.compare_digest` to avoid a timing side-channel, the same
discipline admin_auth.check_admin_password already uses.
"""

import hmac

from fastapi import Header, HTTPException

from app.core.config import get_settings


async def require_provisioning_credential(
    authorization: str | None = Header(default=None),
) -> None:
    """FastAPI dependency — attach to the provisioning router. A
    missing header, a malformed header, and a wrong secret all raise the
    same generic 401 with the same message: this endpoint has no
    "public" state to leak the existence of, so there's no reason to
    distinguish failure modes for the caller."""
    settings = get_settings()

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Provisioning credential required")

    provided = authorization.removeprefix("Bearer ").strip()
    if not provided or not hmac.compare_digest(provided, settings.provisioning_api_key):
        raise HTTPException(status_code=401, detail="Provisioning credential required")

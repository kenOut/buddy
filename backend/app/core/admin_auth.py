"""Manager Portal authentication — a single shared password, not
per-manager accounts (this project has no session-based auth anywhere
else either; this follows the same deliberate simplicity, scoped to
gating the admin/manager surface rather than modeling real identity).

The session itself is a stateless, HMAC-signed cookie value — no new
database table. The server can verify a token's authenticity and
expiry from the token alone; nothing about it is looked up in storage,
so there is nothing to clean up, migrate, or leak from a table.

Token format (before base64url-encoding): `{expires_at}.{signature}`,
where `signature = HMAC-SHA256(secret, str(expires_at))`. Constant-time
comparison (`hmac.compare_digest`) is used throughout to avoid a timing
side-channel on both the password check and the signature check.
"""

import base64
import hmac
import time
from hashlib import sha256

from fastapi import Cookie, HTTPException

from app.core.config import get_settings

SESSION_COOKIE_NAME = "buddy_admin_session"


def _sign(expires_at: int) -> str:
    settings = get_settings()
    return hmac.new(settings.admin_session_secret.encode(), str(expires_at).encode(), sha256).hexdigest()


def create_admin_session_token() -> str:
    settings = get_settings()
    expires_at = int(time.time()) + settings.admin_session_ttl_seconds
    signature = _sign(expires_at)
    raw = f"{expires_at}.{signature}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def verify_admin_session_token(token: str | None) -> bool:
    if not token:
        return False
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        expires_at_str, signature = raw.split(".", 1)
        expires_at = int(expires_at_str)
    except (ValueError, UnicodeDecodeError):
        return False

    if time.time() > expires_at:
        return False
    return hmac.compare_digest(signature, _sign(expires_at))


def check_admin_password(password: str) -> bool:
    settings = get_settings()
    return hmac.compare_digest(password, settings.admin_password)


async def require_admin_session(
    buddy_admin_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> None:
    """FastAPI dependency — attach to any manager-only route (or an
    entire router via `include_router(..., dependencies=[...])`) to
    require a valid session cookie. Raises 401, never silently
    redirects — the frontend decides what to do with a 401; the API
    itself only enforces the boundary."""
    if not verify_admin_session_token(buddy_admin_session):
        raise HTTPException(status_code=401, detail="Manager sign-in required")

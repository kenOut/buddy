from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.admin_auth import (
    SESSION_COOKIE_NAME,
    check_admin_password,
    create_admin_session_token,
    require_admin_session,
    verify_admin_session_token,
)
from app.core.config import get_settings
from app.schemas.admin import AdminLoginRequest, AdminOverview, AdminSessionStatus
from app.services import admin_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/login", response_model=AdminSessionStatus)
async def admin_login(payload: AdminLoginRequest, response: Response):
    """The only unauthenticated write this router exposes, by design —
    everything else here requires an existing valid session."""
    if not check_admin_password(payload.password):
        raise HTTPException(status_code=401, detail="Incorrect password")

    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_admin_session_token(),
        max_age=settings.admin_session_ttl_seconds,
        httponly=True,
        samesite="lax",
        # P5 — Production Security Hardening. Environment-aware, not
        # hardcoded: production is expected to be served over https, so
        # the cookie is marked Secure there (never sent over plain
        # http); local/dev stays over http, where Secure would silently
        # break the cookie entirely.
        secure=settings.environment == "production",
    )
    return AdminSessionStatus(authenticated=True)


@router.post("/logout", response_model=AdminSessionStatus)
async def admin_logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME)
    return AdminSessionStatus(authenticated=False)


@router.get("/session", response_model=AdminSessionStatus)
async def admin_session_status(
    buddy_admin_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
):
    """Never raises — this is the one endpoint the frontend polls to
    decide whether to show the login page, so it just reports the
    current state rather than enforcing it (require_admin_session, used
    everywhere else, is what actually enforces the boundary)."""
    return AdminSessionStatus(authenticated=verify_admin_session_token(buddy_admin_session))


@router.get("/overview", response_model=AdminOverview, dependencies=[Depends(require_admin_session)])
async def get_overview(db: AsyncSession = Depends(get_db)):
    return await admin_service.get_overview(db)

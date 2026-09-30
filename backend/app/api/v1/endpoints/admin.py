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
from app.models import ADMIN_USER_ROLES
from app.schemas.admin import AdminLoginRequest, AdminOverview, AdminSessionStatus
from app.schemas.admin_user import AdminUserCreate, AdminUserRead
from app.services import admin_service, admin_user_service
from app.services.admin_user_service import AdminUserConflictError, InvalidAdminUserRoleError

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/login", response_model=AdminSessionStatus)
async def admin_login(payload: AdminLoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """The only unauthenticated write this router exposes, by design —
    everything else here requires an existing valid session. Two
    credential paths issue the exact same session (see
    AdminLoginRequest's own docstring): the original shared password
    when `email` is omitted, or a specific AdminUser stakeholder
    account when it's supplied. Both failure modes return the identical
    401/"Incorrect password" — this endpoint has no "does this email
    exist" state worth leaking to an unauthenticated caller."""
    if payload.email:
        admin_user = await admin_user_service.authenticate_admin_user(db, payload.email, payload.password)
        if admin_user is None:
            raise HTTPException(status_code=401, detail="Incorrect email or password")
    elif not check_admin_password(payload.password):
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


@router.get("/user-roles", response_model=list[str])
async def list_admin_user_roles():
    """Static, needs no auth — just the fixed role list the "New user
    profile" form's dropdown renders (see ADMIN_USER_ROLES)."""
    return ADMIN_USER_ROLES


@router.get("/users", response_model=list[AdminUserRead], dependencies=[Depends(require_admin_session)])
async def list_admin_users(db: AsyncSession = Depends(get_db)):
    return await admin_user_service.list_admin_users(db)


@router.post(
    "/users", response_model=AdminUserRead, status_code=201, dependencies=[Depends(require_admin_session)]
)
async def create_admin_user(payload: AdminUserCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await admin_user_service.create_admin_user(db, payload)
    except InvalidAdminUserRoleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AdminUserConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

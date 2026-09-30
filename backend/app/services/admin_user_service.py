"""Manager Portal per-user stakeholder accounts (AdminUser) — a second
way to obtain the exact same admin session `require_admin_session`
already checks, alongside the original shared `ADMIN_PASSWORD`
(admin_auth.py, unchanged). See app/models/admin_user.py's own
docstring for why this stays "who is this stakeholder" categorization
rather than a real per-role authorization model.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.password_hashing import hash_password, verify_password
from app.models import ADMIN_USER_ROLES, AdminUser
from app.schemas.admin_user import AdminUserCreate


class AdminUserConflictError(Exception):
    """Raised when the requested email is already in use by another
    AdminUser — mapped to 409 at the endpoint, never a raw
    IntegrityError/500."""


class InvalidAdminUserRoleError(Exception):
    """Raised for a role outside ADMIN_USER_ROLES — mapped to 422 at
    the endpoint. Checked here (not just left to the database's own
    CHECK constraint) so the caller gets a clear, immediate message
    naming the valid values, rather than a raw constraint-violation
    error."""


async def list_admin_users(db: AsyncSession) -> list[AdminUser]:
    result = await db.execute(select(AdminUser).order_by(AdminUser.created_at))
    return list(result.scalars().all())


async def get_admin_user_by_email(db: AsyncSession, email: str) -> AdminUser | None:
    result = await db.execute(select(AdminUser).where(AdminUser.email == email))
    return result.scalars().first()


async def create_admin_user(db: AsyncSession, payload: AdminUserCreate) -> AdminUser:
    if payload.role not in ADMIN_USER_ROLES:
        raise InvalidAdminUserRoleError(
            f"Invalid role: {payload.role!r}. Must be one of {ADMIN_USER_ROLES}."
        )

    admin_user = AdminUser(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(admin_user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AdminUserConflictError(f"An account with email {payload.email!r} already exists.") from exc
    await db.refresh(admin_user)
    return admin_user


async def authenticate_admin_user(db: AsyncSession, email: str, password: str) -> AdminUser | None:
    """Returns the AdminUser on success, or None for every failure mode
    (unknown email, wrong password, deactivated account) — deliberately
    indistinguishable to the caller, the same reasoning
    admin_auth.check_admin_password's single generic 401 already
    follows: this endpoint has no "does this email exist" state worth
    leaking to an unauthenticated caller."""
    admin_user = await get_admin_user_by_email(db, email)
    if admin_user is None or not admin_user.is_active:
        return None
    if not verify_password(password, admin_user.password_hash):
        return None
    return admin_user

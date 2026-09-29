from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

# Scopes the "at most one active invitation per employee" index to rows
# that are still usable — an invitation that has been used or revoked no
# longer occupies the "one active slot", which is exactly what lets
# issuing a fresh invitation coexist with the full, un-deleted history of
# every earlier one. Expiry is deliberately NOT part of this condition:
# it's time-based, so a static index can't express it — the service
# layer (invitation_service.issue_invitation) explicitly revokes any
# existing un-used/un-revoked invitation before creating a new one,
# which is what actually keeps a merely-expired-but-still-"active" row
# from blocking a reissue.
_STILL_ACTIVE = "used_at IS NULL AND revoked_at IS NULL"


class EmployeeInvitation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A temporary credential granting entry into onboarding — distinct
    from OnboardingSession, which represents persistent onboarding
    progress. Deliberately never reuses OnboardingSession.id as a bearer
    token (P1.1 retired the pre-existing `bundle/by-token/{session_token}`
    scaffolding that did exactly that, once this real mechanism existed):
    that conflates "proof you're allowed in" with "your progress record",
    which can't expire, can't be revoked without destroying progress, and
    can't express one employee having several invitations issued over
    time (resend, reissue-after-expiry) against a single onboarding
    session.

    The raw token itself is never persisted anywhere — only
    `token_hash` (see invitation_service._hash_token). Historical rows
    are kept, never deleted, for auditability.
    """

    __tablename__ = "employee_invitations"
    __table_args__ = (
        Index(
            "uq_employee_invitation_active",
            "employee_id",
            unique=True,
            sqlite_where=text(_STILL_ACTIVE),
            postgresql_where=text(_STILL_ACTIVE),
        ),
        Index("uq_employee_invitation_token_hash", "token_hash", unique=True),
    )

    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    employee: Mapped["Employee"] = relationship()

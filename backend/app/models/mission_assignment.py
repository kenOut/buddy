from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class MissionAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mission_assignments"

    mission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    onboarding_session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("onboarding_sessions.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    mission: Mapped["Mission"] = relationship(back_populates="assignments")
    employee: Mapped["Employee"] = relationship(back_populates="mission_assignments")
    onboarding_session: Mapped["OnboardingSession | None"] = relationship(
        back_populates="mission_assignments"
    )

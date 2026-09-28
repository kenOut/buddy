from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Assessment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assessments"

    onboarding_session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("onboarding_sessions.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    answers: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    onboarding_session: Mapped["OnboardingSession"] = relationship(back_populates="assessments")
    employee: Mapped["Employee"] = relationship(back_populates="assessments")

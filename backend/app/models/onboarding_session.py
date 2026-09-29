from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

SCENES = [
    "welcome",
    "department",
    "team",
    "reporting_line",
    "role",
    "missions",
    "assessment",
    "completion",
]


class OnboardingSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "onboarding_sessions"
    __table_args__ = (
        # P2 — Provisioning Boundary. Every read path already assumed
        # "at most one session per employee" (get_or_create_session's own
        # SELECT uses .first()), but nothing enforced it at the database
        # level until now — under real concurrency (eager provisioning
        # calling get_or_create_session from multiple simultaneous
        # requests, or two racing GET /bundle calls before this phase)
        # two callers could both find "no session" and both insert one.
        # This is what makes the IntegrityError-and-recover handling in
        # get_or_create_session an actual guarantee rather than a
        # best-effort check.
        UniqueConstraint("employee_id", name="uq_onboarding_session_employee"),
    )

    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    current_scene: Mapped[str] = mapped_column(String(50), nullable=False, default="welcome")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_started")
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_metadata: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)

    employee: Mapped["Employee"] = relationship(back_populates="onboarding_sessions")
    mission_assignments: Mapped[list["MissionAssignment"]] = relationship(
        back_populates="onboarding_session"
    )
    assessments: Mapped[list["Assessment"]] = relationship(back_populates="onboarding_session")

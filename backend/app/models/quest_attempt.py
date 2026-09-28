from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

QUEST_ATTEMPT_STATUSES = ["NOT_STARTED", "IN_PROGRESS", "SUBMITTED", "EVALUATING", "COMPLETED"]


class QuestAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per (quest, employee) — never more, never fewer. Same
    upsert-through-the-lifecycle pattern as MissionAttempt: the same row is
    reused across not_started -> in_progress -> submitted -> completed, so
    resuming a quest can never duplicate attempts.

    `submission` is deliberately generic JSON rather than typed columns
    (contrast MissionAttempt's affected_service/likely_cause) — Stage 1
    doesn't yet define the submission shape per quest type (a BUILD
    submission looks nothing like an INVESTIGATE one), and that structure
    is intentionally left to a later stage rather than guessed at now.
    """

    __tablename__ = "quest_attempts"
    __table_args__ = (
        UniqueConstraint("quest_id", "employee_id", name="uq_quest_attempt_quest_employee"),
    )

    quest_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("quests.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="NOT_STARTED")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    submission: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    quest: Mapped["Quest"] = relationship(back_populates="attempts")
    employee: Mapped["Employee"] = relationship()

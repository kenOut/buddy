from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

ATTEMPT_STATUSES = ["not_started", "in_progress", "submitted", "completed"]


class MissionAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per (mission, employee) — never more, never fewer. The same
    row is upserted through the full lifecycle (not_started -> in_progress
    -> submitted -> completed) rather than creating a new row per attempt,
    so reopening a mission can never duplicate attempts and an unfinished
    attempt is always resumable from exactly this row."""

    __tablename__ = "mission_attempts"
    __table_args__ = (
        UniqueConstraint("mission_id", "employee_id", name="uq_mission_attempt_mission_employee"),
    )

    mission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_started")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Investigation state — filled in as the employee works, ahead of submit.
    affected_service: Mapped[str | None] = mapped_column(String(120), nullable=True)
    likely_cause: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Also doubles as the freeform "describe your work" submission for
    # reflection-workspace missions — same field, same trust boundary
    # (never contains an answer key either way), just a different prompt
    # on the frontend depending on Mission.workspace_type.
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_viewed: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Quiz-workspace state: {question_id: selected_option}. Never holds
    # the answer key (mission_quizzes.py's `correct_option` never leaves
    # that module) — same trust boundary as evidence_viewed above.
    quiz_answers: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Set only by the server, at submission time. The answer key that
    # produces these is never sent to the client (mission_scenarios.py).
    score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    mission: Mapped["Mission"] = relationship()
    employee: Mapped["Employee"] = relationship()

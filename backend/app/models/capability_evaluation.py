from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin, utcnow


class CapabilityEvaluation(UUIDPrimaryKeyMixin, Base):
    """One AI interpretation of one completed attempt — the audit trail
    for an AI decision. At most one per attempt (idempotent: re-requesting
    evaluation returns the existing record rather than creating another).
    Raw provider output is kept separate from the Pydantic-validated
    structured result, so a parsing/validation change later can be
    re-applied to history without having lost the original.

    Phase 3B Stage 5: generalized to support either a MissionAttempt or a
    QuestAttempt — exactly one of mission_attempt_id/quest_attempt_id is
    populated (CHECK constraint below). The single UniqueConstraint on
    mission_attempt_id from Phase 3A is replaced by two partial unique
    indexes, since a plain UNIQUE(mission_attempt_id) wouldn't stop
    duplicate quest evaluations (every quest-sourced row has
    mission_attempt_id = NULL, and NULL != NULL in SQL) — same reasoning
    as QuestAssignment's per-type partial indexes from Stage 3.
    """

    __tablename__ = "capability_evaluations"
    __table_args__ = (
        CheckConstraint(
            "(mission_attempt_id IS NOT NULL AND quest_attempt_id IS NULL) OR "
            "(mission_attempt_id IS NULL AND quest_attempt_id IS NOT NULL)",
            name="ck_capability_evaluation_single_attempt",
        ),
        Index(
            "uq_capability_evaluation_mission_attempt",
            "mission_attempt_id",
            unique=True,
            sqlite_where=text("mission_attempt_id IS NOT NULL"),
            postgresql_where=text("mission_attempt_id IS NOT NULL"),
        ),
        Index(
            "uq_capability_evaluation_quest_attempt",
            "quest_attempt_id",
            unique=True,
            sqlite_where=text("quest_attempt_id IS NOT NULL"),
            postgresql_where=text("quest_attempt_id IS NOT NULL"),
        ),
    )

    mission_attempt_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("mission_attempts.id", ondelete="CASCADE"), nullable=True
    )
    quest_attempt_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("quest_attempts.id", ondelete="CASCADE"), nullable=True
    )
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )

    model: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    evaluation_version: Mapped[str] = mapped_column(String(20), nullable=False)

    raw_response: Mapped[str] = mapped_column(Text, nullable=False)
    structured_result: Mapped[dict] = mapped_column(JSON, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    mission_attempt: Mapped["MissionAttempt | None"] = relationship()
    quest_attempt: Mapped["QuestAttempt | None"] = relationship()
    employee: Mapped["Employee"] = relationship()

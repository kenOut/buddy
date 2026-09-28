from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

EVIDENCE_TYPES = [
    "METRICS",
    "LOGS",
    "SERVICES",
    "TIMELINE",
    "SCREENSHOT",
    "DOCUMENT",
    "CODE",
    "DATASET",
    "TEXT",
    "OTHER",
]


class QuestEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Information the employee is allowed to inspect while working a
    Quest — employee-visible *by definition*. This is a structurally
    separate model from QuestEvaluationCriterion (server-only), not a
    single mixed-visibility table with a flag: there is no field on this
    model, and never should be, that hides part of a row from the
    employee — if content shouldn't reach the employee, it doesn't belong
    here at all.

    `content` is generic JSON so one evidence_type-tagged model can carry
    a metric reading, a log line, a screenshot URL, a code snippet, or
    free text without a table per type.
    """

    __tablename__ = "quest_evidence"

    quest_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("quests.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    quest: Mapped["Quest"] = relationship(back_populates="evidence")

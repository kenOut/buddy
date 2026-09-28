from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

TASK_TYPES = [
    "INVESTIGATE",
    "ANALYZE",
    "DESIGN",
    "BUILD",
    "FIX",
    "EXPLAIN",
    "CREATE",
    "OTHER",
]


class QuestTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One employee action a Quest asks for (e.g. "identify the affected
    service", "implement the fix", "explain your reasoning"). Employee-
    visible by definition — this is the work itself, not its evaluation.
    Generic across quest types: an INVESTIGATE quest's tasks look nothing
    like a BUILD quest's, but both are just an ordered list of these.
    """

    __tablename__ = "quest_tasks"

    quest_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("quests.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    quest: Mapped["Quest"] = relationship(back_populates="tasks")

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

# What kind of evaluation this criterion drives, for a future evaluation
# engine to dispatch on — not evaluation logic itself (none exists yet):
#   DETERMINISTIC — checkable by exact/rule match against expected_answer
#                    (e.g. "the affected service is checkout-service")
#   BEHAVIORAL    — checkable by whether an expected action/behavior was
#                    observed, described in expected_behavior (e.g. "ran
#                    the tests before submitting")
#   QUALITATIVE   — not exactly checkable; reference_solution is guidance
#                    for a future (Stage 5) AI interpreter, not an answer
#                    key to match against
CRITERION_TYPES = ["DETERMINISTIC", "BEHAVIORAL", "QUALITATIVE"]


class QuestEvaluationCriterion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Server-only evaluation source of truth for a Quest. Structurally
    separate from QuestEvidence/QuestTask — nothing on this model is ever
    serialized into an employee-facing response (see schemas/quest.py's
    EmployeeQuestResponse, which has no field capable of carrying this
    model's data at all). This is what "employee-visible" vs "server-only"
    being physically separate concepts means in practice: it's not a flag
    to check, it's a different model with its own response schema.

    No evaluation logic runs against these fields yet (Stage 2 is content
    only) — they're the source of truth a later evaluation engine reads.
    """

    __tablename__ = "quest_evaluation_criteria"

    quest_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("quests.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    criterion_type: Mapped[str] = mapped_column(String(20), nullable=False)

    expected_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_behavior: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_solution: Mapped[str | None] = mapped_column(Text, nullable=True)

    max_score: Mapped[float] = mapped_column(Numeric, nullable=False, default=100)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    quest: Mapped["Quest"] = relationship(back_populates="evaluation_criteria")

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin, utcnow

# Small, deterministic taxonomy — extensible later without a migration
# (it's a plain string column, not a DB-level CHECK-constrained enum, so
# a new type can be added by extending this list alone). NEXT_QUEST is
# the only type Phase 6D actually produces.
RECOMMENDATION_TYPES = ["NEXT_QUEST"]


class Recommendation(UUIDPrimaryKeyMixin, Base):
    """Phase 6D — an immutable historical record of one recommendation
    Buddy made to an employee. Append-only by design: there is no
    service function or endpoint anywhere that updates or deletes a row
    here once created (see services/recommendation_service.py).

    A Recommendation is NOT an assignment, an attempt, a completion, or a
    capability profile — it is a snapshot of "why Buddy suggested this
    Quest, at this moment, given what was known then." `reason`,
    `target_capabilities`, and `capability_snapshot` are captured at
    creation time and never recomputed — if the employee's capabilities
    change later, this row still accurately describes what was true when
    it was created. Only quest_recommendation.py's live ranking produces
    *new* rows going forward; it never rewrites old ones.

    `context_hash` is the deterministic fingerprint (employee_id +
    recommendation_type + quest_id + sorted target_capabilities + each
    target capability's level at that moment) used to decide whether a
    fresh GET should reuse the most recent row for this
    (employee, recommendation_type) or create a new historical entry —
    see recommendation_persistence.py. It is not a uniqueness constraint:
    the same Quest may legitimately be recommended again in a later
    development cycle, producing a new row with a different hash (or
    even the same hash, if development genuinely looped back to an
    identical state — that's still a real, distinct event in time).
    """

    __tablename__ = "recommendations"

    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    quest_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("quests.id", ondelete="CASCADE"), nullable=False
    )
    recommendation_type: Mapped[str] = mapped_column(String(30), nullable=False, default="NEXT_QUEST")

    reason: Mapped[str] = mapped_column(Text, nullable=False)
    target_capabilities: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    capability_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    employee: Mapped["Employee"] = relationship()
    quest: Mapped["Quest"] = relationship()

    __table_args__ = (
        Index("idx_recommendations_employee_created", "employee_id", "created_at"),
        Index(
            "idx_recommendations_employee_type_created",
            "employee_id",
            "recommendation_type",
            "created_at",
        ),
        Index("idx_recommendations_quest", "quest_id"),
    )

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin, utcnow


class QuestCapability(UUIDPrimaryKeyMixin, Base):
    """Maps a Quest to an existing Phase 3A Capability, with a relative
    weight expressing how central that capability is to the Quest (e.g.
    troubleshooting=1.0, documentation=0.5). Purely descriptive metadata
    in Stage 2 — no scoring logic reads this yet; that's Stage 5's job
    (QuestAttempt evidence -> CapabilityEvidence -> CapabilityProfile).

    Does not modify Capability/CapabilityProfile/CapabilityEvidence/
    CapabilityEvaluation at all — this is a new join table pointing at
    the existing, untouched Capability model.
    """

    __tablename__ = "quest_capabilities"
    __table_args__ = (
        UniqueConstraint("quest_id", "capability_id", name="uq_quest_capability_quest_capability"),
    )

    quest_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("quests.id", ondelete="CASCADE"), nullable=False
    )
    capability_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("capabilities.id", ondelete="CASCADE"), nullable=False
    )

    weight: Mapped[float] = mapped_column(Numeric, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    quest: Mapped["Quest"] = relationship(back_populates="capabilities")
    capability: Mapped["Capability"] = relationship()

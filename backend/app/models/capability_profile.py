from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin, utcnow

# NOT_OBSERVED is not "poor performance" — it means no evidence exists yet.
# See services/capability_aggregation.py for the deterministic rules that
# move a profile between these levels.
CAPABILITY_LEVELS = ["NOT_OBSERVED", "DEVELOPING", "CAPABLE", "STRONG"]


class CapabilityProfile(UUIDPrimaryKeyMixin, Base):
    """One row per (employee, capability) — upserted as new evidence
    arrives, the same "single row, never duplicated" pattern as
    MissionAttempt. This is a rollup, not raw data; CapabilityEvidence is
    the source of truth this gets recomputed from."""

    __tablename__ = "capability_profiles"
    __table_args__ = (
        UniqueConstraint("employee_id", "capability_id", name="uq_capability_profile_employee_capability"),
    )

    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    capability_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("capabilities.id", ondelete="CASCADE"), nullable=False
    )

    level: Mapped[str] = mapped_column(String(20), nullable=False, default="NOT_OBSERVED")
    score: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    confidence: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    employee: Mapped["Employee"] = relationship()
    capability: Mapped["Capability"] = relationship()

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin, utcnow

# Same qualitative scale as CapabilityProfile.level, minus NOT_OBSERVED —
# evidence that exists is, by definition, an observation, so it always
# lands somewhere on this scale. Reusing the vocabulary keeps aggregation
# (Stage 8) simple to explain: a profile's level is just a rollup of its
# evidence's strengths.
EVIDENCE_STRENGTHS = ["DEVELOPING", "CAPABLE", "STRONG"]

EVIDENCE_SOURCES = ["deterministic", "ai"]


class CapabilityEvidence(UUIDPrimaryKeyMixin, Base):
    """One observed, explainable data point supporting a capability —
    never fabricated, always traceable back to a specific attempt and
    (for AI-sourced evidence) a specific evaluation record.

    Phase 3B Stage 5: generalized to trace back to either a MissionAttempt
    or a QuestAttempt — exactly one of mission_attempt_id/quest_attempt_id
    is populated, enforced by the CHECK constraint below (same pattern as
    QuestAssignment's single-target constraint from Stage 3). Existing
    Mission-sourced rows are unaffected: mission_attempt_id keeps working
    exactly as before, just now nullable at the schema level to make room
    for the quest_attempt_id sibling.
    """

    __tablename__ = "capability_evidence"
    __table_args__ = (
        CheckConstraint(
            "(mission_attempt_id IS NOT NULL AND quest_attempt_id IS NULL) OR "
            "(mission_attempt_id IS NULL AND quest_attempt_id IS NOT NULL)",
            name="ck_capability_evidence_single_attempt",
        ),
    )

    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    mission_attempt_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("mission_attempts.id", ondelete="CASCADE"), nullable=True
    )
    quest_attempt_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("quest_attempts.id", ondelete="CASCADE"), nullable=True
    )
    capability_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("capabilities.id", ondelete="CASCADE"), nullable=False
    )
    evaluation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("capability_evaluations.id", ondelete="CASCADE"), nullable=True
    )

    evidence_type: Mapped[str] = mapped_column(String(60), nullable=False)
    observation: Mapped[str] = mapped_column(Text, nullable=False)
    strength: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    employee: Mapped["Employee"] = relationship()
    mission_attempt: Mapped["MissionAttempt | None"] = relationship()
    quest_attempt: Mapped["QuestAttempt | None"] = relationship()
    capability: Mapped["Capability"] = relationship()
    evaluation: Mapped["CapabilityEvaluation | None"] = relationship()

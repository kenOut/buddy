from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin, utcnow

# Stable keys — referenced by CapabilityEvidence/Profile and by the AI
# evaluation contract. Seeded once at startup (seed/capabilities.py),
# idempotently, independent of the demo org/employee seed data.
CAPABILITY_KEYS = [
    "technical_understanding",
    "troubleshooting",
    "problem_solving",
    "documentation",
    "communication",
    "independence",
]


class Capability(UUIDPrimaryKeyMixin, Base):
    """A named, explainable dimension of workplace capability. This is a
    global reference table — not employee- or organization-scoped."""

    __tablename__ = "capabilities"

    key: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

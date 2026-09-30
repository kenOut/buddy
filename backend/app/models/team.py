from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Team(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Phase A — Team Entity & Department -> Team Foundation. A named
    sub-grouping within exactly one Department (Department -> Team is
    1-to-many, same shape as Department -> Role/Project), replacing what
    was previously only a free-text `Employee.team` string with no real
    structure behind it (see the Team Architecture Impact Audit).

    `Employee.team_id` does not exist yet — that's Phase B. This model
    is deliberately introduced on its own first, with nothing else in
    the app referencing it yet, so the schema/API foundation can be
    verified in isolation before any employee-facing behavior changes.
    """

    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("department_id", "name", name="uq_team_department_name"),
    )

    department_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    department: Mapped["Department"] = relationship(back_populates="teams")

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Department(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "departments"

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="departments")
    roles: Mapped[list["Role"]] = relationship(back_populates="department")
    employees: Mapped[list["Employee"]] = relationship(back_populates="department")
    projects: Mapped[list["Project"]] = relationship(back_populates="department")
    missions: Mapped[list["Mission"]] = relationship(back_populates="department")
    # Phase A — Team Entity & Department -> Team Foundation.
    # `cascade="all, delete-orphan"` at the ORM level, on top of the
    # `teams.department_id` FK's own `ondelete="CASCADE"` — the same
    # reasoning Quest's own child relationships already established
    # (see quest.py's docstring): SQLite, this project's dev/test
    # database, never enforces FK pragmas, so a DB-level ON DELETE
    # CASCADE alone silently does nothing there. Without this, deleting
    # a Department via the ORM (the only way this app ever deletes
    # anything) fails with a NOT NULL constraint error instead of
    # cascading, since `Team.department_id` is non-nullable. No other
    # Department relationship above has this — deliberately left
    # unchanged, since this fix is scoped to the new Team relationship
    # only.
    teams: Mapped[list["Team"]] = relationship(back_populates="department", cascade="all, delete-orphan")

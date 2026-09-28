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

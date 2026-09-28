from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Employee(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "employees"

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    role_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="SET NULL"), nullable=True
    )
    manager_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    supervisor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # A sub-team/branch within the department (e.g. "FinOps"/"TechOps"
    # inside Engineering) — deliberately a plain free-text label, not a
    # foreign key to a new table: it's a grouping for display purposes
    # only (Team scene), not an org-structure concept anything else in
    # the app depends on.
    team: Mapped[str | None] = mapped_column(String(100), nullable=True)
    employment_type: Mapped[str] = mapped_column(String(50), nullable=False, default="full_time")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="invited")

    organization: Mapped["Organization"] = relationship(back_populates="employees")
    department: Mapped["Department | None"] = relationship(back_populates="employees")
    role: Mapped["Role | None"] = relationship(back_populates="employees")
    manager: Mapped["Employee | None"] = relationship(
        remote_side="Employee.id", foreign_keys=[manager_id]
    )
    supervisor: Mapped["Employee | None"] = relationship(
        remote_side="Employee.id", foreign_keys=[supervisor_id]
    )
    onboarding_sessions: Mapped[list["OnboardingSession"]] = relationship(back_populates="employee")
    mission_assignments: Mapped[list["MissionAssignment"]] = relationship(back_populates="employee")
    assessments: Mapped[list["Assessment"]] = relationship(back_populates="employee")

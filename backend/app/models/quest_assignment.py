from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

ASSIGNMENT_TYPES = ["EMPLOYEE", "DEPARTMENT", "ROLE"]

# One condition per assignment_type, reused for both the CHECK constraint
# (exactly one target populated) and the three partial unique indexes
# below (uniqueness scoped to rows of that type only).
_EMPLOYEE_TARGET = "assignment_type = 'EMPLOYEE'"
_DEPARTMENT_TARGET = "assignment_type = 'DEPARTMENT'"
_ROLE_TARGET = "assignment_type = 'ROLE'"


class QuestAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Who is eligible to receive a Quest. Exactly one of
    employee_id/department_id/role_id is populated, matching
    `assignment_type` — enforced by a real CHECK constraint, not just
    Pydantic validation, since this is a correctness property of the row
    itself, not just of one API's input.

    Reuses the existing, already-normalized `Role` model (role_id) rather
    than a free-text role/title string or a new Role subsystem — Employee
    already has a `role_id` FK to the same table, so matching on it during
    eligibility resolution (quest_assignment_service.is_employee_eligible)
    is a direct equality check, not a string comparison.
    """

    __tablename__ = "quest_assignments"
    __table_args__ = (
        CheckConstraint(
            f"({_EMPLOYEE_TARGET} AND employee_id IS NOT NULL AND department_id IS NULL AND role_id IS NULL) OR "
            f"({_DEPARTMENT_TARGET} AND department_id IS NOT NULL AND employee_id IS NULL AND role_id IS NULL) OR "
            f"({_ROLE_TARGET} AND role_id IS NOT NULL AND employee_id IS NULL AND department_id IS NULL)",
            name="ck_quest_assignment_single_target",
        ),
        # Partial unique indexes — a plain UniqueConstraint on nullable
        # columns wouldn't prevent duplicates (NULL != NULL in SQL), and
        # only one of the three target columns is ever populated on a
        # given row. Both sqlite_where and postgresql_where are set so
        # this is a real, enforced guarantee on SQLite (dev/test) too,
        # not just on Postgres — same reasoning as Stage 2's ORM-level
        # cascade workaround for SQLite's FK pragma being off.
        Index(
            "uq_quest_assignment_employee",
            "quest_id",
            "employee_id",
            unique=True,
            sqlite_where=text(_EMPLOYEE_TARGET),
            postgresql_where=text(_EMPLOYEE_TARGET),
        ),
        Index(
            "uq_quest_assignment_department",
            "quest_id",
            "department_id",
            unique=True,
            sqlite_where=text(_DEPARTMENT_TARGET),
            postgresql_where=text(_DEPARTMENT_TARGET),
        ),
        Index(
            "uq_quest_assignment_role",
            "quest_id",
            "role_id",
            unique=True,
            sqlite_where=text(_ROLE_TARGET),
            postgresql_where=text(_ROLE_TARGET),
        ),
    )

    quest_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("quests.id", ondelete="CASCADE"), nullable=False
    )
    assignment_type: Mapped[str] = mapped_column(String(20), nullable=False)

    employee_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=True
    )
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="CASCADE"), nullable=True
    )
    role_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=True
    )

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Phase 8B — Workspace Access Automation foundation. Whether this
    # specific assignment is required for the target's onboarding
    # readiness (see WorkspaceAccessGrant). Deliberately lives here, not
    # on Quest: the same Quest can be assigned to multiple targets, and
    # whether it's mandatory is a property of the assignment (e.g.
    # required for one department's onboarding, optional elsewhere), not
    # an intrinsic property of the Quest itself. Defaults False so every
    # existing assignment stays non-required until a manager opts one in
    # — no existing quest becomes required automatically.
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    quest: Mapped["Quest"] = relationship(back_populates="assignments")
    employee: Mapped["Employee | None"] = relationship()
    department: Mapped["Department | None"] = relationship()
    role: Mapped["Role | None"] = relationship()

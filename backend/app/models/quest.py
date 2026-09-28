from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

QUEST_TYPES = [
    "INVESTIGATE",
    "TROUBLESHOOT",
    "FIX",
    "BUILD",
    "DESIGN",
    "ANALYZE",
    "CREATE_SOLUTION",
    "OTHER",
]

QUEST_STATUSES = ["DRAFT", "PUBLISHED", "ARCHIVED"]

WORKSPACE_TYPES = ["INVESTIGATION", "DESIGN", "BUILD", "FIX", "ANALYSIS", "GENERAL", "TROUBLESHOOT"]

QUEST_DIFFICULTIES = ["EASY", "MEDIUM", "HARD", "EXPERT"]


class Quest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A manager-authored work challenge — the general-purpose successor to
    the developer-defined Mission catalog (see Phase 3B Stage 0 report).
    Coexists with Mission/MissionAttempt rather than replacing them; the
    existing onboarding checklist and the SRE investigation mission keep
    running through the Mission domain untouched.

    Deliberately minimal in Stage 1: identity/classification fields only.
    Tasks, evidence, evaluation criteria, capability mapping, prerequisites
    and assignment are separate models added in later stages, not columns
    bolted onto this one.
    """

    __tablename__ = "quests"

    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    created_by_employee_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    quest_type: Mapped[str] = mapped_column(String(30), nullable=False)
    workspace_type: Mapped[str] = mapped_column(String(30), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")

    # project/department/created_by are one-way — Project/Department/
    # Employee are not modified to add a reverse side, keeping this
    # addition fully additive (see Phase 3B Stage 0 report §18). `attempts`
    # is paired with QuestAttempt.quest via back_populates since both
    # sides target the same FK column and SQLAlchemy needs the link made
    # explicit to avoid an overlapping-relationship warning.
    project: Mapped["Project | None"] = relationship()
    department: Mapped["Department | None"] = relationship()
    created_by: Mapped["Employee | None"] = relationship()
    attempts: Mapped[list["QuestAttempt"]] = relationship(back_populates="quest")

    # Stage 2 content children. `cascade="all, delete-orphan"` is applied
    # at the ORM level (not just the FK's ondelete="CASCADE") because
    # SQLite — the local dev/test database — never has foreign_keys
    # enforcement turned on in this project, so a DB-level ON DELETE
    # CASCADE silently does nothing there; the ORM-level cascade is what
    # actually deletes these rows when a Quest is deleted via `db.delete`,
    # on both SQLite and Postgres.
    tasks: Mapped[list["QuestTask"]] = relationship(
        back_populates="quest", order_by="QuestTask.sort_order", cascade="all, delete-orphan"
    )
    evidence: Mapped[list["QuestEvidence"]] = relationship(
        back_populates="quest", order_by="QuestEvidence.sort_order", cascade="all, delete-orphan"
    )
    evaluation_criteria: Mapped[list["QuestEvaluationCriterion"]] = relationship(
        back_populates="quest",
        order_by="QuestEvaluationCriterion.sort_order",
        cascade="all, delete-orphan",
    )
    capabilities: Mapped[list["QuestCapability"]] = relationship(
        back_populates="quest", cascade="all, delete-orphan"
    )

    # Stage 3. Same ORM-level cascade reasoning as the Stage 2 children
    # above.
    assignments: Mapped[list["QuestAssignment"]] = relationship(
        back_populates="quest", cascade="all, delete-orphan"
    )

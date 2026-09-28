from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Mission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "missions"

    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    mission_type: Mapped[str] = mapped_column(String(50), nullable=False, default="task")
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # What kind of work environment this Mission's attempt workspace is —
    # replaces the old "probe /missions/{id}/scenario and 404 means
    # simple" detection with an explicit, honest field (mirrors Quest's
    # own `workspace_type`). "investigation": the existing evidence-panel
    # + deterministic service/cause grading (mission_scenarios.py).
    # "quiz": deterministic multiple-choice comprehension check
    # (mission_quizzes.py) — no AI step, a quiz has nothing for a
    # qualitative reader to add on top of a right/wrong answer.
    # "reflection": a freeform "describe your work" submission, completed
    # once it clears a real-effort bar, then read live by the same AI
    # provider Quests and investigation Missions already use. Defaults to
    # "reflection" — the one shape every mission can honestly support
    # with no bespoke content required.
    workspace_type: Mapped[str] = mapped_column(String(20), nullable=False, default="reflection")

    # Whether completing this Mission is required for readiness (see
    # readiness_service.py). Lives on Mission itself, not MissionAssignment
    # — unlike QuestAssignment.required, there's no polymorphic per-target
    # complexity here: `ensure_assignments_for_employee` creates exactly
    # one assignment per (mission, employee) pair via a straight
    # department match, so "required for this employee" and "required as
    # this Mission is configured" are the same fact, not two. Defaults
    # False so every existing/new Mission stays optional until an admin
    # opts it in — mirrors QuestAssignment.required's own default.
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    project: Mapped["Project | None"] = relationship(back_populates="missions")
    department: Mapped["Department | None"] = relationship(back_populates="missions")
    assignments: Mapped[list["MissionAssignment"]] = relationship(back_populates="mission")

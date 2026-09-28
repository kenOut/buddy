from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, utcnow

WORKSPACE_ACCESS_STATUSES = ["PENDING", "GRANTED", "FAILED", "REVOKED"]


class WorkspaceAccessGrant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per (employee, workspace_integration) — never more, never
    fewer (Phase 8A/8B — Workspace Access Automation foundation). The
    `(employee_id, workspace_integration_id)` unique constraint below is
    the primary idempotency mechanism for granting access: whatever
    triggers a grant attempt (not implemented yet — see Phase 8C) must
    get-or-create against this row rather than insert unconditionally,
    the same upsert-through-the-lifecycle pattern QuestAttempt and
    MissionAssignment already use for their own (parent, employee)
    uniqueness.

    `provider_ref`/`last_error`/`attempt_count` are operational fields
    for the provider integration and manager-facing views only — never
    employee-facing (see schemas/workspace_access.py's employee-safe
    schema, which excludes them along with `external_ref` on the
    integration side).

    `provider_ref` is an opaque, provider-specific identifier for the
    external grant (Phase 8F-1 formalization) — eventually a Google
    Drive permission ID, but stored and read verbatim everywhere in this
    codebase, never parsed or pattern-matched. No code may branch on its
    shape or prefix; doing so would leak a provider-specific assumption
    into otherwise provider-agnostic code (see workspace_provider.py's
    module docstring).
    """

    __tablename__ = "workspace_access_grants"
    __table_args__ = (
        UniqueConstraint(
            "employee_id", "workspace_integration_id", name="uq_workspace_access_grant_employee_integration"
        ),
    )

    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    workspace_integration_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspace_integrations.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # One-way, same reasoning as WorkspaceIntegration.department — Employee
    # and WorkspaceIntegration are not modified to add reverse accessors.
    employee: Mapped["Employee"] = relationship()
    workspace_integration: Mapped["WorkspaceIntegration"] = relationship()

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

WORKSPACE_PROVIDERS = ["google_drive"]


class WorkspaceIntegration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A department's configured external workspace (Phase 8A/8B —
    Workspace Access Automation foundation). One row per department:
    `department_id` is unique, matching the "one active/configured
    workspace per department for MVP" scope decision — not a general
    many-workspaces-per-department model.

    `external_ref` is an opaque external resource identifier, meaningful
    only to whichever provider is configured for this row (Phase 8F-1
    formalization) — for the eventual Google Drive provider it will hold
    a Shared Drive ID, but the core application must never assume that,
    parse it, or otherwise interpret its shape; only the provider
    implementation (see services/workspace_provider.py) may do that.
    Provider plumbing only — it must never appear in an employee-facing
    response schema; only `display_name`/`workspace_link` are safe for
    that (see schemas/workspace_access.py). This model itself holds no
    credentials — auth material for the provider lives in server
    config/settings, never in a domain row.
    """

    __tablename__ = "workspace_integrations"

    department_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    external_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    workspace_link: Mapped[str] = mapped_column(String(1000), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # One-way, same as Quest.department — Department is not modified to
    # add a reverse accessor, keeping this addition fully additive.
    department: Mapped["Department"] = relationship()

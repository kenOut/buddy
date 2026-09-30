from sqlalchemy import Boolean, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

# Fixed role categories for a stakeholder account — not tied to the
# Department model (a "People & Culture" or "Security & IT" stakeholder
# account exists independently of whether a real Department row with
# that name exists yet). A short, explicit, CHECK-enforced list, same
# reasoning as ASSIGNMENT_TYPES/EVIDENCE_SOURCES elsewhere in this
# project.
ADMIN_USER_ROLES = ["people_culture", "security_it", "departments"]


class AdminUser(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A named Manager Portal login, distinct from the single shared
    `ADMIN_PASSWORD` (admin_auth.py) that has been this project's only
    admin credential since P1. An AdminUser authenticates with their own
    email/password (see core/password_hashing.py) and, once
    authenticated, receives the exact same session cookie/permissions
    the shared password already grants — this project has no concept of
    restricted admin roles yet, so `role` here is a categorization label
    for who this stakeholder is, not an authorization scope.

    `password_hash` is never serialized in any API response — see
    schemas/admin_user.py's AdminUserRead, which has no field for it at
    all, the same structural guarantee EmailSendResult uses for
    credentials.
    """

    __tablename__ = "admin_users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('people_culture', 'security_it', 'departments')",
            name="ck_admin_user_role",
        ),
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

from datetime import datetime

from pydantic import Field

from app.schemas.common import ORMBase


class AdminUserCreate(ORMBase):
    email: str
    full_name: str
    password: str = Field(min_length=8)
    role: str


class AdminUserLogin(ORMBase):
    email: str
    password: str


class AdminUserRead(ORMBase):
    """No `password_hash` field, structurally — the same "cannot leak
    what it has no field for" guarantee EmailSendResult uses for
    credentials."""

    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

from datetime import date, datetime

from app.schemas.common import ORMBase


class EmployeeCreate(ORMBase):
    organization_id: str
    department_id: str | None = None
    role_id: str | None = None
    manager_id: str | None = None
    supervisor_id: str | None = None
    full_name: str
    email: str
    job_title: str | None = None
    team: str | None = None
    employment_type: str = "full_time"
    start_date: date | None = None
    avatar_url: str | None = None
    status: str = "invited"
    # P1 — Identity & Invitation Foundation. Nullable: most employees
    # created today (demo seed, admin UI) have no external identity
    # provider yet. Never use email as this key.
    identity_provider: str | None = None
    external_subject: str | None = None


class EmployeeSummary(ORMBase):
    """Lightweight nested representation used for manager/supervisor/teammates."""

    id: str
    full_name: str
    email: str
    job_title: str | None
    team: str | None
    avatar_url: str | None


class EmployeeRead(ORMBase):
    id: str
    organization_id: str
    department_id: str | None
    role_id: str | None
    manager_id: str | None
    supervisor_id: str | None
    full_name: str
    email: str
    job_title: str | None
    team: str | None
    employment_type: str
    start_date: date | None
    avatar_url: str | None
    status: str
    identity_provider: str | None
    external_subject: str | None
    created_at: datetime
    updated_at: datetime


class EmployeeStatusUpdate(ORMBase):
    status: str


class EmployeeDepartmentUpdate(ORMBase):
    department_id: str | None = None

from app.schemas.common import ORMBase
from app.schemas.department import DepartmentRead
from app.schemas.employee import EmployeeRead
from app.schemas.onboarding_session import OnboardingSessionRead


class EmployeeOnboardingRow(ORMBase):
    employee: EmployeeRead
    department: DepartmentRead | None
    session: OnboardingSessionRead | None
    missions_completed: int
    missions_total: int


class AdminOverview(ORMBase):
    total_employees: int
    onboarding_in_progress: int
    onboarding_completed: int
    total_departments: int
    rows: list[EmployeeOnboardingRow]


class AdminLoginRequest(ORMBase):
    """`email` is optional and backward compatible: omitted (or blank),
    this is the original shared-password login (check_admin_password);
    supplied, this authenticates as that specific AdminUser stakeholder
    account instead (see admin.py's admin_login and
    admin_user_service.authenticate_admin_user). Both paths issue the
    exact same session cookie/permissions."""

    email: str | None = None
    password: str


class AdminSessionStatus(ORMBase):
    authenticated: bool

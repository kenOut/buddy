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
    password: str


class AdminSessionStatus(ORMBase):
    authenticated: bool

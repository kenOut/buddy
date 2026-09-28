from app.schemas.common import ORMBase
from app.schemas.department import DepartmentRead
from app.schemas.employee import EmployeeRead, EmployeeSummary
from app.schemas.mission import MissionAssignmentRead
from app.schemas.onboarding_session import OnboardingSessionRead
from app.schemas.organization import OrganizationRead
from app.schemas.project import ProjectRead
from app.schemas.role import RoleRead


class AssessmentQuestionOption(ORMBase):
    id: str
    label: str


class AssessmentQuestion(ORMBase):
    id: str
    prompt: str
    options: list[AssessmentQuestionOption]


class OnboardingBundle(ORMBase):
    """Everything the /onboarding scene experience needs, in one call."""

    employee: EmployeeRead
    organization: OrganizationRead
    department: DepartmentRead | None
    role: RoleRead | None
    manager: EmployeeSummary | None
    supervisor: EmployeeSummary | None
    teammates: list[EmployeeSummary]
    projects: list[ProjectRead]
    session: OnboardingSessionRead
    mission_assignments: list[MissionAssignmentRead]
    assessment_questions: list[AssessmentQuestion]

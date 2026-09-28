from datetime import datetime

from app.schemas.common import ORMBase


class OnboardingSessionRead(ORMBase):
    id: str
    employee_id: str
    current_scene: str
    status: str
    progress_percent: int
    started_at: datetime | None
    completed_at: datetime | None


class OnboardingSessionUpdate(ORMBase):
    current_scene: str | None = None
    status: str | None = None

from fastapi import APIRouter, Depends

from app.api.v1.endpoints import (
    admin,
    analytics,
    capabilities,
    departments,
    employees,
    invitations,
    mission_attempts,
    missions,
    onboarding,
    organizations,
    projects,
    provisioning,
    quest_assignments,
    quest_capabilities,
    quest_evaluation_criteria,
    quest_evidence,
    quest_tasks,
    quests,
    roles,
)
from app.core.admin_auth import require_admin_session

# Manager Portal (/admin/*) surface only — never applied to a router the
# employee-facing onboarding flow touches (onboarding, capabilities,
# mission_attempts stay open; quests.router is mixed and gated
# per-endpoint instead, inside quests.py itself). See admin.py's own
# /admin/login, /admin/logout, /admin/session, which are deliberately
# NOT behind this dependency — those are how a session gets established
# or checked in the first place.
_admin_only = [Depends(require_admin_session)]

api_router = APIRouter()
api_router.include_router(organizations.router, dependencies=_admin_only)
api_router.include_router(departments.router, dependencies=_admin_only)
api_router.include_router(roles.router, dependencies=_admin_only)
api_router.include_router(employees.router, dependencies=_admin_only)
api_router.include_router(projects.router, dependencies=_admin_only)
api_router.include_router(missions.router, dependencies=_admin_only)
api_router.include_router(mission_attempts.router)
api_router.include_router(onboarding.router)
# Mixed router, like quests.router below — issuing an invitation is
# admin-gated per-route inside invitations.py itself; exchanging one is
# the employee-facing entry point and must stay open.
api_router.include_router(invitations.router)
# A third, distinct trust boundary from both _admin_only above and the
# employee session — gated by its own provisioning credential entirely
# inside provisioning.py (core/provisioning_auth.py), never the admin
# cookie. See provisioning_service's module docstring.
api_router.include_router(provisioning.router)
api_router.include_router(admin.router)
api_router.include_router(capabilities.router)
api_router.include_router(quests.router)
api_router.include_router(quest_tasks.router, dependencies=_admin_only)
api_router.include_router(quest_evidence.router, dependencies=_admin_only)
api_router.include_router(quest_evaluation_criteria.router, dependencies=_admin_only)
api_router.include_router(quest_capabilities.router, dependencies=_admin_only)
api_router.include_router(quest_assignments.router, dependencies=_admin_only)
api_router.include_router(analytics.router, dependencies=_admin_only)

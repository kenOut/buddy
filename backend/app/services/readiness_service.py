"""ReadinessService — Phase 8D.

Answers the question Phase 8C's WorkspaceAccessService deliberately does
NOT answer: "has this employee completed all requirements to be ready?"
`is_ready()` is a pure, derived computation — nothing about readiness is
stored anywhere (no READY_FOR_WORK column exists or is added here). It
is recomputed fresh on every call from OnboardingSession/QuestAssignment/
QuestAttempt, so a manager adding a new required assignment after an
employee was previously ready is reflected correctly the very next time
readiness is checked, with no cache to invalidate.

Readiness predicate (exactly, no more):

    OnboardingSession.status == "completed"
    AND at least one required-and-eligible PUBLISHED Quest exists for
        this employee
    AND every required-and-eligible PUBLISHED Quest has a COMPLETED
        QuestAttempt for this employee
    AND every required Mission in this employee's department has a
        COMPLETED MissionAssignment for this employee

An employee with onboarding complete but zero required quests is
deliberately NOT ready — there is nothing to be "ready" for yet, and an
admin has to opt at least one Quest in via `QuestAssignment.required`
before this can ever become true. This is intentional, not an oversight
(see Phase 8B's model docstring on why `required` defaults False).

Missions deliberately do NOT get the same "at least one must exist"
floor: zero required Missions leaves the Mission side of the gate
vacuously satisfied rather than permanently blocking readiness. Quests
already carry that floor as this system's one deliberate "an admin must
opt in before anyone can ever be ready" safeguard — a second, identical
floor on Missions would only add a redundant footgun (every existing
department would need a required Mission configured or no employee in
it could ever become ready) without changing what this feature is for:
Missions are an *additional* gate that engages once an admin marks one
required, not a second copy of the same opt-in-required mechanism.
Once at least one Mission in a department is required, that Mission
must be completed for any employee in that department to be ready,
exactly like a required Quest.

`check_and_trigger()` is the one function anything outside this module
should call. It is meant to run only AFTER a QuestAttempt or
MissionAssignment has been durably committed as COMPLETED — see the
call sites in quest_evaluation_service.evaluate_attempt and
mission_service.update_assignment_status, all of which call this after
their own `await db.commit()`, never before or instead of it. This
module never mutates QuestAttempt/QuestAssignment/MissionAssignment/
OnboardingSession/CapabilityEvidence/CapabilityProfile/Recommendation
itself — it only reads them and, when ready, calls into
workspace_access_service.ensure_access (Phase 8C), which is already
idempotent and already isolates provider failure to WorkspaceAccessGrant
alone. check_and_trigger additionally never lets any exception escape —
a bug in readiness/workspace machinery must never turn a successful
Quest or Mission completion into a failed API response, on top of never
being able to undo the already-committed row that triggered it.

Quest eligibility reuses the exact EMPLOYEE/DEPARTMENT/ROLE matching
rules quest_assignment_service.get_matching_assignment_types already
defines as the single authoritative definition of "who can attempt this
Quest" — not a second, independently-invented notion of eligibility.
It cannot simply call that per-quest function in a loop, though: that
function answers "is this employee eligible via ANY assignment"
regardless of `required`, which would incorrectly count a Quest as
required-for-this-employee if they happen to also match a *different*,
non-required assignment on the same Quest. The query below instead
scopes the same three matching rules directly to `required=True`
assignments up front, so only an assignment that is BOTH required AND
matches this employee can make a Quest count.

Mission eligibility has no equivalent multi-target complexity to work
around: `mission_service.ensure_assignments_for_employee` creates
exactly one MissionAssignment per (Mission, employee) pair via a
straight `Mission.department_id == employee.department_id` match, so
`required_eligible_mission_ids` below is a direct query against Mission
itself, not a resolution over a separate assignment-eligibility table.

Phase 8H-1: `is_ready()` and `get_readiness_summary()` both call the
same `_compute_readiness_state()` — one computation, two views onto it
(a bare bool vs. the fuller employee-safe counts) — rather than two
independently-maintained readiness algorithms that could silently drift
apart. `ReadinessSummary.ready` and `is_ready()`'s return value are
therefore identical by construction for the same database state, not
merely by convention; see test_readiness_summary.py's explicit
agreement tests for the proof.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models import (
    Employee,
    Mission,
    MissionAssignment,
    OnboardingSession,
    Quest,
    QuestAssignment,
    QuestAttempt,
    WorkspaceAccessGrant,
    WorkspaceIntegration,
)
from app.schemas.readiness import EmployeeReadinessSummary
from app.services import workspace_access_service


async def _onboarding_completed(db: AsyncSession, employee_id: str) -> bool:
    stmt = select(OnboardingSession.status).where(OnboardingSession.employee_id == employee_id)
    result = await db.execute(stmt)
    status = result.scalar_one_or_none()
    return status == "completed"


async def required_eligible_quest_ids(db: AsyncSession, employee: Employee) -> set[str]:
    """Every PUBLISHED Quest with a required=True, active=True
    assignment that matches this employee directly (EMPLOYEE), via their
    department (DEPARTMENT), or via their role (ROLE) — the same three
    rules quest_assignment_service.get_matching_assignment_types applies
    for ordinary (non-required) eligibility, scoped here to required
    assignments only (see module docstring for why a per-quest reuse of
    that function would be incorrect).

    Public (Phase 8H-3, promoted from a private helper — pure rename,
    no behavior change) specifically so the employee-facing Quest
    response enrichment (`required_for_readiness` on EmployeeQuestResponse,
    see api/v1/endpoints/quests.py and capabilities.py) can check set
    membership against the exact same query is_ready() itself uses,
    rather than a second, independently-written eligibility query that
    could silently drift from this one."""
    match_conditions = [
        (QuestAssignment.assignment_type == "EMPLOYEE") & (QuestAssignment.employee_id == employee.id)
    ]
    if employee.department_id is not None:
        match_conditions.append(
            (QuestAssignment.assignment_type == "DEPARTMENT")
            & (QuestAssignment.department_id == employee.department_id)
        )
    if employee.role_id is not None:
        match_conditions.append(
            (QuestAssignment.assignment_type == "ROLE") & (QuestAssignment.role_id == employee.role_id)
        )

    stmt = (
        select(QuestAssignment.quest_id)
        .join(Quest, Quest.id == QuestAssignment.quest_id)
        .where(
            QuestAssignment.required.is_(True),
            QuestAssignment.active.is_(True),
            Quest.status == "PUBLISHED",
            or_(*match_conditions),
        )
        .distinct()
    )
    result = await db.execute(stmt)
    return set(result.scalars().all())


async def _completed_quest_ids(db: AsyncSession, employee_id: str, quest_ids: set[str]) -> set[str]:
    if not quest_ids:
        return set()
    stmt = select(QuestAttempt.quest_id).where(
        QuestAttempt.employee_id == employee_id,
        QuestAttempt.quest_id.in_(quest_ids),
        QuestAttempt.status == "COMPLETED",
    )
    result = await db.execute(stmt)
    return set(result.scalars().all())


async def required_eligible_mission_ids(db: AsyncSession, employee: Employee) -> set[str]:
    """Every Mission with `required=True` in this employee's own
    department (see module docstring for why this needs no separate
    assignment-eligibility resolution the way Quests do). An employee
    with no department has no eligible missions at all — mirrors
    `ensure_assignments_for_employee`'s own guard, which never runs for
    a department-less employee."""
    if employee.department_id is None:
        return set()
    stmt = select(Mission.id).where(
        Mission.required.is_(True),
        Mission.department_id == employee.department_id,
    )
    result = await db.execute(stmt)
    return set(result.scalars().all())


async def _completed_mission_ids(db: AsyncSession, employee_id: str, mission_ids: set[str]) -> set[str]:
    if not mission_ids:
        return set()
    stmt = select(MissionAssignment.mission_id).where(
        MissionAssignment.employee_id == employee_id,
        MissionAssignment.mission_id.in_(mission_ids),
        MissionAssignment.status == "completed",
    )
    result = await db.execute(stmt)
    return set(result.scalars().all())


@dataclass
class _ReadinessState:
    """The one computation both is_ready() and get_readiness_summary()
    read from — never recomputed independently. Deliberately internal
    (not exported): callers outside this module get either the bare
    bool (is_ready) or the employee-safe schema (get_readiness_summary),
    never this raw shape."""

    onboarding_completed: bool
    required_quest_ids: set[str]
    completed_required_quest_ids: set[str]
    required_mission_ids: set[str]
    completed_required_mission_ids: set[str]

    @property
    def required_quest_count(self) -> int:
        return len(self.required_quest_ids)

    @property
    def completed_required_quest_count(self) -> int:
        return len(self.completed_required_quest_ids)

    @property
    def remaining_required_quest_count(self) -> int:
        return self.required_quest_count - self.completed_required_quest_count

    @property
    def required_mission_count(self) -> int:
        return len(self.required_mission_ids)

    @property
    def completed_required_mission_count(self) -> int:
        return len(self.completed_required_mission_ids)

    @property
    def remaining_required_mission_count(self) -> int:
        return self.required_mission_count - self.completed_required_mission_count

    @property
    def ready(self) -> bool:
        # Zero required quests is deliberately NOT ready — see module
        # docstring. `required_quest_ids <= completed_required_quest_ids`
        # is vacuously true for an empty required set, so that must be
        # checked explicitly rather than falling out of the subset test.
        # Missions get no equivalent `bool(required_mission_ids)` check —
        # also per the module docstring — so a department with zero
        # required Missions leaves this term vacuously True instead of
        # permanently blocking readiness.
        return (
            self.onboarding_completed
            and bool(self.required_quest_ids)
            and self.required_quest_ids <= self.completed_required_quest_ids
            and self.required_mission_ids <= self.completed_required_mission_ids
        )


async def _compute_readiness_state(db: AsyncSession, employee: Employee) -> _ReadinessState:
    """Always computes all three pieces, even when onboarding isn't
    done or the required set is empty — unlike is_ready()'s original
    short-circuiting shape, because get_readiness_summary() needs real
    counts to show regardless of which piece is currently blocking
    readiness (an employee should be able to see "onboarding not done
    yet, and 2 of 3 required quests remain" at the same time, not have
    the second half hidden because the first was false). This costs at
    most one extra query when required_quest_ids is empty —
    _completed_quest_ids already short-circuits internally on an empty
    input, so it's not a wasted round trip even then."""
    onboarding_completed = await _onboarding_completed(db, employee.id)
    required_quest_ids = await required_eligible_quest_ids(db, employee)
    completed_quest_ids = await _completed_quest_ids(db, employee.id, required_quest_ids)
    required_mission_ids = await required_eligible_mission_ids(db, employee)
    completed_mission_ids = await _completed_mission_ids(db, employee.id, required_mission_ids)
    return _ReadinessState(
        onboarding_completed=onboarding_completed,
        required_quest_ids=required_quest_ids,
        completed_required_quest_ids=completed_quest_ids,
        required_mission_ids=required_mission_ids,
        completed_required_mission_ids=completed_mission_ids,
    )


async def is_ready(db: AsyncSession, employee: Employee) -> bool:
    state = await _compute_readiness_state(db, employee)
    return state.ready


async def get_readiness_summary(db: AsyncSession, employee: Employee) -> EmployeeReadinessSummary:
    """Phase 8H-1 — the employee-safe, fully-derived read model. Never
    stores anything; recomputed fresh from current OnboardingSession/
    QuestAssignment/QuestAttempt state on every call, exactly like
    is_ready() itself. Exposes only counts — never a Quest id, title, or
    assignment detail — so there is nothing here for a future consumer
    to accidentally treat as more than a summary (a required-quest list
    is a deliberately separate, not-yet-built concern — see the Phase 8H
    architecture inspection's proposed 8H-3)."""
    state = await _compute_readiness_state(db, employee)
    return EmployeeReadinessSummary(
        ready=state.ready,
        onboarding_completed=state.onboarding_completed,
        required_quest_count=state.required_quest_count,
        completed_required_quest_count=state.completed_required_quest_count,
        remaining_required_quest_count=state.remaining_required_quest_count,
        required_mission_count=state.required_mission_count,
        completed_required_mission_count=state.completed_required_mission_count,
        remaining_required_mission_count=state.remaining_required_mission_count,
    )


async def get_readiness_milestone_timestamp(db: AsyncSession, employee: Employee) -> datetime | None:
    """Phase 8H-2, corrected — the timestamp associated with the
    employee CURRENTLY satisfying the readiness requirement set, or
    None if they currently do not. Does not modify is_ready()/
    _compute_readiness_state() at all (Phase 8H-2's own constraint) — it
    calls is_ready() unchanged, then reuses _required_eligible_quest_
    ids() (the exact same eligibility resolution, not a re-derived one)
    for the one extra thing readiness itself doesn't need: the actual
    completion *timestamps* of the required quest attempts
    (_compute_readiness_state only needs their ids, to check set
    membership, never their timestamps).

    Semantic correction (Phase 8H-2 correction pass) — read this
    carefully, it is a deliberate, load-bearing distinction, not a
    caveat to skim: this function does NOT answer "when did the
    employee first become ready" and must never be described, logged,
    or documented as if it did. There is no persisted readiness history
    in this system (by design — the Phase 8H architecture inspection's
    own conclusion: prefer derived state over persisted history), so
    "first ever" is not a question this codebase can honestly answer at
    all. What this function DOES answer, precisely: "assuming the
    employee is ready right now, what timestamp is associated with
    satisfying today's requirement set" — computed fresh from
    OnboardingSession.completed_at and the CURRENTLY required quests'
    and missions' completion timestamps, every single call, exactly like
    is_ready() itself is recomputed fresh every call. If the required set
    changes (a required quest is archived, a required mission is turned
    optional, or a new one of either is added) — is_ready()
    can flip to False, this function then returns None, and the
    Development Journey's READINESS_REACHED item simply stops appearing.
    That disappearance is correct, expected behavior, not a bug: the
    item represents "currently satisfies readiness," and it is
    dishonest to keep showing it once that stops being true.

    Returns None (not a fabricated timestamp) if is_ready() is True but
    OnboardingSession.completed_at is somehow unset — that combination
    would itself be a data inconsistency, not a normal outcome, so
    nothing is invented to paper over it.
    """
    if not await is_ready(db, employee):
        return None

    session_stmt = select(OnboardingSession.completed_at).where(
        OnboardingSession.employee_id == employee.id
    )
    onboarding_completed_at = (await db.execute(session_stmt)).scalar_one_or_none()
    if onboarding_completed_at is None:
        return None

    required_quest_ids = await required_eligible_quest_ids(db, employee)
    attempts_stmt = select(QuestAttempt.completed_at).where(
        QuestAttempt.employee_id == employee.id,
        QuestAttempt.quest_id.in_(required_quest_ids),
        QuestAttempt.status == "COMPLETED",
    )
    result = await db.execute(attempts_stmt)
    completed_ats = [c for c in result.scalars().all() if c is not None]

    required_mission_ids = await required_eligible_mission_ids(db, employee)
    missions_stmt = select(MissionAssignment.completed_at).where(
        MissionAssignment.employee_id == employee.id,
        MissionAssignment.mission_id.in_(required_mission_ids),
        MissionAssignment.status == "completed",
    )
    mission_result = await db.execute(missions_stmt)
    completed_ats += [c for c in mission_result.scalars().all() if c is not None]

    if not completed_ats:
        return onboarding_completed_at
    return max(onboarding_completed_at, max(completed_ats))


async def _get_active_integration(db: AsyncSession, department_id: str) -> WorkspaceIntegration | None:
    stmt = select(WorkspaceIntegration).where(
        WorkspaceIntegration.department_id == department_id,
        WorkspaceIntegration.active.is_(True),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def check_and_trigger(employee_id: str) -> WorkspaceAccessGrant | None:
    """Call only after a QuestAttempt has been durably committed as
    COMPLETED. Idempotent and safe to call on every evaluate_attempt
    return path that observes a COMPLETED attempt, including one that
    was already COMPLETED before this call — readiness is recomputed
    fresh each time and workspace_access_service.ensure_access is itself
    idempotent (see its own docstring), so repeated calls never create
    duplicate grants or re-invoke the provider once GRANTED.

    Deliberately opens its own AsyncSessionLocal() rather than reusing
    the caller's session, for two reasons: (1) it makes the "only after
    the Quest transaction is durably committed" boundary a real,
    physical one — this runs in a separate connection/transaction that
    starts strictly after evaluate_attempt's own commit, not merely
    after the same commit call returns on a session that's still in
    scope; (2) it keeps this call's extra reads (Employee,
    OnboardingSession, WorkspaceIntegration, WorkspaceAccessGrant) from
    adding load onto the request's own session during the exact window
    concurrent Quest-evaluation requests contend on it.

    Returns None (never raises) if: the employee doesn't exist, isn't
    ready yet, has no department, has no active WorkspaceIntegration
    configured for their department, or if anything at all goes wrong
    while checking — this function's contract is "never able to affect
    the caller," not "always able to grant access."
    """
    try:
        async with AsyncSessionLocal() as db:
            employee = await db.get(Employee, employee_id)
            if employee is None:
                return None

            if not await is_ready(db, employee):
                return None

            if employee.department_id is None:
                return None

            integration = await _get_active_integration(db, employee.department_id)
            if integration is None:
                return None

            return await workspace_access_service.ensure_access(db, employee_id, integration.id)
    except Exception:
        # See docstring above: a bug here must never surface as a
        # failure of the Quest evaluation call that triggered it. The
        # QuestAttempt this was called after is already committed, on a
        # different session, and unaffected regardless.
        return None

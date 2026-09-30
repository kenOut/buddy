"""ReadinessService — Phase 8D, extended by Stage 2 (Performance-Aware
Readiness).

Answers the question Phase 8C's WorkspaceAccessService deliberately does
NOT answer: "has this employee completed all requirements to be ready?"
`is_ready()` is a pure, derived computation — nothing about readiness is
stored anywhere (no READY_FOR_WORK column exists or is added here). It
is recomputed fresh on every call from OnboardingSession/QuestAssignment/
QuestAttempt/MissionAssignment/MissionAttempt, so a manager adding a new
required assignment (or a new performance threshold) after an employee
was previously ready is reflected correctly the very next time readiness
is checked, with no cache to invalidate.

Readiness predicate (exactly, no more):

    OnboardingSession.status == "completed"
    AND at least one required-and-eligible PUBLISHED Quest exists for
        this employee
    AND every required-and-eligible PUBLISHED Quest is SATISFIED
    AND every required Mission in this employee's department is
        SATISFIED

A required item is SATISFIED when:
    - it is completed (QuestAttempt.status == "COMPLETED" for Quests;
      MissionAssignment.status == "completed" for Missions), AND
    - EITHER its configured minimum_score is NULL ("completion is
      sufficient" — the exact pre-Stage-2 behavior, preserved for every
      assignment that has never had a threshold configured), OR the
      relevant attempt's persisted score is >= that minimum_score.

An incomplete required item is never satisfied regardless of any
threshold — a threshold only ever makes an ALREADY-completed item
harder to count, it never provides a way to skip completion (see
RequiredItemState.satisfied below; Stage 2 §5/§9's own explicit rule).

Stage 2 is deliberately NOT:

    ready = average(all required scores) >= some bar

Averaging is never computed anywhere in this module. Each required item
is evaluated independently, against its own configured threshold (or
lack of one) — a strong score on one required item can never compensate
for a weak score on another, and neither can a strong score on an
OPTIONAL item ever count toward a required one. See RequiredItemState
and _build_blockers below for the actual, non-averaging predicate.

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
must be SATISFIED (not merely completed, as of Stage 2) for any
employee in that department to be ready, exactly like a required Quest.

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
being able to undo the already-committed row that triggered it. Stage 2
changes nothing about this function's own logic — it calls the now-
stricter is_ready() unchanged, so a below-threshold completion simply
never reaches ensure_access, with zero new code here (Stage 2 §17).

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

Stage 2 threshold source, per kind (Stage 2 §4): `Mission.minimum_score`
(alongside `Mission.required` — no per-assignment override exists for
Missions, same reasoning `required` itself already documents) and
`QuestAssignment.minimum_score` (alongside `QuestAssignment.required` —
the same Quest can be assigned to multiple targets with different bars,
exactly like `required` already varies per assignment). Where an
employee matches more than one required QuestAssignment for the same
Quest (a real but rare shape — e.g. a personal EMPLOYEE assignment and
their DEPARTMENT's assignment on the same Quest), the STRICTEST
(highest) configured threshold among them wins; a NULL only yields if
every matching required assignment leaves the threshold unconfigured.

Phase 8H-1: `is_ready()` and `get_readiness_summary()` both call the
same `_compute_readiness_state()` — one computation, two views onto it
(a bare bool vs. the fuller employee-safe counts) — rather than two
independently-maintained readiness algorithms that could silently drift
apart. `ReadinessSummary.ready` and `is_ready()`'s return value are
therefore identical by construction for the same database state, not
merely by convention; see test_readiness_summary.py's explicit
agreement tests for the proof. Stage 2's `get_readiness_blockers()`
reads from the exact same `_compute_readiness_state()` call too — three
views on one computation, never three.
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
    MissionAttempt,
    OnboardingSession,
    Quest,
    QuestAssignment,
    QuestAttempt,
    WorkspaceAccessGrant,
    WorkspaceIntegration,
)
from app.schemas.readiness import EmployeeReadinessSummary, ReadinessBlocker
from app.services import workspace_access_service


async def _onboarding_completed(db: AsyncSession, employee_id: str) -> bool:
    stmt = select(OnboardingSession.status).where(OnboardingSession.employee_id == employee_id)
    result = await db.execute(stmt)
    status = result.scalar_one_or_none()
    return status == "completed"


async def _required_quest_assignment_rows(
    db: AsyncSession, employee: Employee
) -> list[tuple[str, str, float | None]]:
    """(quest_id, title, minimum_score) for every required+active+
    PUBLISHED assignment matching this employee — the same three
    matching rules quest_assignment_service.get_matching_assignment_types
    applies for ordinary (non-required) eligibility, scoped here to
    required assignments only (see module docstring for why a per-quest
    reuse of that function would be incorrect). A Quest can appear more
    than once here if the employee matches multiple required
    assignments on it — callers that need one row per Quest (the id-set
    helper, and the threshold/title resolution below) merge duplicates
    themselves."""
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
        select(QuestAssignment.quest_id, Quest.title, QuestAssignment.minimum_score)
        .join(Quest, Quest.id == QuestAssignment.quest_id)
        .where(
            QuestAssignment.required.is_(True),
            QuestAssignment.active.is_(True),
            Quest.status == "PUBLISHED",
            or_(*match_conditions),
        )
    )
    result = await db.execute(stmt)
    return list(result.all())


async def required_eligible_quest_ids(db: AsyncSession, employee: Employee) -> set[str]:
    """Every PUBLISHED Quest with a required=True, active=True
    assignment that matches this employee directly (EMPLOYEE), via their
    department (DEPARTMENT), or via their role (ROLE).

    Public (Phase 8H-3, promoted from a private helper — pure rename,
    no behavior change) specifically so the employee-facing Quest
    response enrichment (`required_for_readiness` on EmployeeQuestResponse,
    see api/v1/endpoints/quests.py and capabilities.py) can check set
    membership against the exact same query is_ready() itself uses,
    rather than a second, independently-written eligibility query that
    could silently drift from this one. Unchanged by Stage 2 — still a
    bare id set, still the same query — so every existing caller keeps
    working exactly as before; threshold data is available separately
    via `required_quest_items` below for callers that need it."""
    rows = await _required_quest_assignment_rows(db, employee)
    return {quest_id for quest_id, _title, _threshold in rows}


async def _quest_attempt_rows(
    db: AsyncSession, employee_id: str, quest_ids: set[str]
) -> dict[str, tuple[str, float | None]]:
    """quest_id -> (status, score) for whichever QuestAttempt exists —
    at most one per (quest, employee), the model's own invariant."""
    if not quest_ids:
        return {}
    stmt = select(QuestAttempt.quest_id, QuestAttempt.status, QuestAttempt.score).where(
        QuestAttempt.employee_id == employee_id,
        QuestAttempt.quest_id.in_(quest_ids),
    )
    result = await db.execute(stmt)
    return {quest_id: (status, score) for quest_id, status, score in result.all()}


async def required_eligible_mission_ids(db: AsyncSession, employee: Employee) -> set[str]:
    """Every Mission with `required=True` in this employee's own
    department (see module docstring for why this needs no separate
    assignment-eligibility resolution the way Quests do). An employee
    with no department has no eligible missions at all — mirrors
    `ensure_assignments_for_employee`'s own guard, which never runs for
    a department-less employee. Unchanged by Stage 2 — still a bare id
    set; threshold data is available separately via
    `required_mission_items` below."""
    rows = await _required_mission_rows(db, employee)
    return {mission_id for mission_id, _title, _threshold in rows}


async def _required_mission_rows(
    db: AsyncSession, employee: Employee
) -> list[tuple[str, str, float | None]]:
    """(mission_id, title, minimum_score) for every required Mission in
    this employee's department."""
    if employee.department_id is None:
        return []
    stmt = select(Mission.id, Mission.title, Mission.minimum_score).where(
        Mission.required.is_(True),
        Mission.department_id == employee.department_id,
    )
    result = await db.execute(stmt)
    return list(result.all())


async def _mission_assignment_status_by_id(
    db: AsyncSession, employee_id: str, mission_ids: set[str]
) -> dict[str, str]:
    if not mission_ids:
        return {}
    stmt = select(MissionAssignment.mission_id, MissionAssignment.status).where(
        MissionAssignment.employee_id == employee_id,
        MissionAssignment.mission_id.in_(mission_ids),
    )
    result = await db.execute(stmt)
    return dict(result.all())


async def _mission_scores_by_id(
    db: AsyncSession, employee_id: str, mission_ids: set[str]
) -> dict[str, float | None]:
    """The current MissionAttempt.score per mission_id — the single
    upserted row for (mission, employee), so this is inherently "the
    current valid completed attempt" per Stage 2 §11/§23's own framing:
    Missions have no separate attempt-history model (a deliberately
    out-of-scope concern for this stage — see §22), so the row a passing
    submit last wrote IS the only row there is."""
    if not mission_ids:
        return {}
    stmt = select(MissionAttempt.mission_id, MissionAttempt.score).where(
        MissionAttempt.employee_id == employee_id,
        MissionAttempt.mission_id.in_(mission_ids),
    )
    result = await db.execute(stmt)
    return dict(result.all())


@dataclass
class RequiredItemState:
    """One required Mission or Quest's readiness-relevant state — the
    single source both `_ReadinessState.ready` and `_build_blockers`
    read from, so "is this item satisfied" is defined exactly once.

    `completed` keeps its exact pre-Stage-2 meaning (QuestAttempt.status
    == "COMPLETED", or MissionAssignment.status == "completed") —
    completion and performance are deliberately different facts (Stage 2
    §34's own "Completion means the employee did the work; performance
    thresholds determine whether the work was good enough" principle),
    never collapsed into one flag.
    """

    id: str
    title: str
    completed: bool
    score: float | None
    minimum_score: float | None

    @property
    def satisfied(self) -> bool:
        if not self.completed:
            return False
        if self.minimum_score is None:
            return True
        if self.score is None:
            # A completed-but-scoreless item is a data inconsistency,
            # not a normal outcome (every submit path sets score
            # unconditionally — see mission_attempt_service.py/
            # quest_evaluation_service.py) — treated as NOT satisfying a
            # configured threshold rather than silently passing it.
            return False
        return self.score >= self.minimum_score


async def required_quest_items(db: AsyncSession, employee: Employee) -> list[RequiredItemState]:
    """Public (Stage 2) for the same reason `required_eligible_quest_ids`
    already is — so manager_performance_service can read the exact same
    per-item satisfied/completed/score/minimum_score state
    readiness_service itself computed, rather than a second,
    independently-derived copy of it (Stage 2 §8)."""
    rows = await _required_quest_assignment_rows(db, employee)
    if not rows:
        return []

    titles: dict[str, str] = {}
    thresholds: dict[str, float | None] = {}
    for quest_id, title, minimum_score in rows:
        titles[quest_id] = title
        if quest_id not in thresholds:
            thresholds[quest_id] = minimum_score
        elif minimum_score is not None:
            current = thresholds[quest_id]
            thresholds[quest_id] = minimum_score if current is None else max(current, minimum_score)

    attempts = await _quest_attempt_rows(db, employee.id, set(thresholds))
    items = []
    for quest_id, threshold in thresholds.items():
        status, score = attempts.get(quest_id, (None, None))
        items.append(
            RequiredItemState(
                id=quest_id,
                title=titles[quest_id],
                completed=(status == "COMPLETED"),
                score=score,
                minimum_score=threshold,
            )
        )
    return items


async def required_mission_items(db: AsyncSession, employee: Employee) -> list[RequiredItemState]:
    """Public (Stage 2) — see required_quest_items's own docstring."""
    rows = await _required_mission_rows(db, employee)
    if not rows:
        return []

    mission_ids = {mission_id for mission_id, _title, _threshold in rows}
    statuses = await _mission_assignment_status_by_id(db, employee.id, mission_ids)
    scores = await _mission_scores_by_id(db, employee.id, mission_ids)

    items = []
    for mission_id, title, minimum_score in rows:
        items.append(
            RequiredItemState(
                id=mission_id,
                title=title,
                completed=(statuses.get(mission_id) == "completed"),
                score=scores.get(mission_id),
                minimum_score=minimum_score,
            )
        )
    return items


@dataclass
class _ReadinessState:
    """The one computation both is_ready() and get_readiness_summary()
    (and, as of Stage 2, get_readiness_blockers()) read from — never
    recomputed independently. Deliberately internal (not exported):
    callers outside this module get the bare bool (is_ready), the
    employee-safe schema (get_readiness_summary), or the manager-safe
    structured blockers (get_readiness_blockers), never this raw shape.
    """

    onboarding_completed: bool
    required_quest_items: list[RequiredItemState]
    required_mission_items: list[RequiredItemState]

    @property
    def required_quest_count(self) -> int:
        return len(self.required_quest_items)

    @property
    def completed_required_quest_count(self) -> int:
        # Completion, not satisfaction — see RequiredItemState's own
        # docstring on why these stay different facts.
        return sum(1 for item in self.required_quest_items if item.completed)

    @property
    def remaining_required_quest_count(self) -> int:
        return self.required_quest_count - self.completed_required_quest_count

    @property
    def required_mission_count(self) -> int:
        return len(self.required_mission_items)

    @property
    def completed_required_mission_count(self) -> int:
        return sum(1 for item in self.required_mission_items if item.completed)

    @property
    def remaining_required_mission_count(self) -> int:
        return self.required_mission_count - self.completed_required_mission_count

    @property
    def required_items_below_threshold(self) -> int:
        """Completed, but not satisfied — i.e. blocked by score, not by
        being unfinished. Distinct from `remaining_required_*_count`
        above, which counts unfinished items."""
        all_items = self.required_quest_items + self.required_mission_items
        return sum(1 for item in all_items if item.completed and not item.satisfied)

    @property
    def ready(self) -> bool:
        # Zero required quests is deliberately NOT ready — see module
        # docstring. Missions get no equivalent "at least one required"
        # floor — also per the module docstring — so a department with
        # zero required Missions leaves that term vacuously True.
        # Stage 2: `all(item.satisfied ...)` replaces the old subset
        # check (`required_ids <= completed_ids`) — when every item's
        # minimum_score is NULL, `satisfied` reduces to exactly
        # `completed`, so this is behavior-identical to the pre-Stage-2
        # predicate for every assignment that has never had a threshold
        # configured. No average is computed anywhere in this property.
        return (
            self.onboarding_completed
            and bool(self.required_quest_items)
            and all(item.satisfied for item in self.required_quest_items)
            and all(item.satisfied for item in self.required_mission_items)
        )


async def _compute_readiness_state(db: AsyncSession, employee: Employee) -> _ReadinessState:
    """Always computes all three pieces, even when onboarding isn't
    done or the required set is empty — unlike is_ready()'s original
    short-circuiting shape, because get_readiness_summary() needs real
    counts to show regardless of which piece is currently blocking
    readiness (an employee should be able to see "onboarding not done
    yet, and 2 of 3 required quests remain" at the same time, not have
    the second half hidden because the first was false)."""
    onboarding_completed = await _onboarding_completed(db, employee.id)
    quest_items = await required_quest_items(db, employee)
    mission_items = await required_mission_items(db, employee)
    return _ReadinessState(
        onboarding_completed=onboarding_completed,
        required_quest_items=quest_items,
        required_mission_items=mission_items,
    )


def _build_blockers(state: _ReadinessState) -> list[ReadinessBlocker]:
    """Manager-safe, structured blockers — built from exactly the
    RequiredItemState list `state.ready` itself evaluated, never a
    second, independently-derived notion of "why not ready" (Stage 2
    §8/§12). Sorted by title within each group so the order is stable
    across calls against unchanged data."""
    blockers: list[ReadinessBlocker] = []
    if not state.onboarding_completed:
        blockers.append(
            ReadinessBlocker(
                type="ONBOARDING_INCOMPLETE", item_id=None, title="Onboarding", score=None, minimum_score=None
            )
        )

    for item in sorted(state.required_mission_items, key=lambda i: i.title):
        if item.satisfied:
            continue
        blocker_type = "REQUIRED_MISSION_INCOMPLETE" if not item.completed else "REQUIRED_MISSION_BELOW_THRESHOLD"
        blockers.append(
            ReadinessBlocker(
                type=blocker_type, item_id=item.id, title=item.title, score=item.score,
                minimum_score=item.minimum_score,
            )
        )

    for item in sorted(state.required_quest_items, key=lambda i: i.title):
        if item.satisfied:
            continue
        blocker_type = "REQUIRED_QUEST_INCOMPLETE" if not item.completed else "REQUIRED_QUEST_BELOW_THRESHOLD"
        blockers.append(
            ReadinessBlocker(
                type=blocker_type, item_id=item.id, title=item.title, score=item.score,
                minimum_score=item.minimum_score,
            )
        )

    return blockers


async def is_ready(db: AsyncSession, employee: Employee) -> bool:
    state = await _compute_readiness_state(db, employee)
    return state.ready


async def get_readiness_summary(db: AsyncSession, employee: Employee) -> EmployeeReadinessSummary:
    """Phase 8H-1 — the employee-safe, fully-derived read model. Never
    stores anything; recomputed fresh from current OnboardingSession/
    QuestAssignment/QuestAttempt/MissionAssignment/MissionAttempt state
    on every call, exactly like is_ready() itself. Exposes only counts
    — never a Quest/Mission id, title, score, or assignment detail — so
    there is nothing here for a future consumer to accidentally treat
    as more than a summary. See get_readiness_blockers below for the
    manager-safe, per-item view Stage 2 adds alongside this."""
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
        required_items_below_threshold=state.required_items_below_threshold,
    )


async def get_readiness_blockers(db: AsyncSession, employee: Employee) -> list[ReadinessBlocker]:
    """Stage 2 — the manager-safe, structured view of exactly why an
    employee is or isn't ready. Includes real score/minimum_score
    values, so this is deliberately a SEPARATE function from
    get_readiness_summary above, never merged into it or called from an
    employee-facing endpoint — see ReadinessBlocker's own docstring for
    why. manager_performance_service.py is this function's one caller;
    it does not re-derive blocker logic of its own (Stage 2 §8)."""
    state = await _compute_readiness_state(db, employee)
    return _build_blockers(state)


async def get_readiness_milestone_timestamp(db: AsyncSession, employee: Employee) -> datetime | None:
    """Phase 8H-2, corrected — the timestamp associated with the
    employee CURRENTLY satisfying the readiness requirement set, or
    None if they currently do not. Does not modify is_ready()/
    _compute_readiness_state() at all (Phase 8H-2's own constraint) — it
    calls is_ready() unchanged (Stage 2's stricter definition included,
    with no code change needed here), then reuses required_eligible_
    quest_ids/required_eligible_mission_ids (the exact same eligibility
    resolution, not a re-derived one) for the one extra thing readiness
    itself doesn't need: the actual completion *timestamps* of the
    required items (_compute_readiness_state only needs score/status,
    never timestamps).

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
    or a threshold changes (a required quest is archived, a required
    mission is turned optional, a minimum_score is raised past an
    employee's existing score, or a new one of either is added) —
    is_ready() can flip to False, this function then returns None, and
    the Development Journey's READINESS_REACHED item simply stops
    appearing. That disappearance is correct, expected behavior, not a
    bug: the item represents "currently satisfies readiness," and it is
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

    Stage 2 changes nothing about this function's own body — it still
    calls `is_ready()` exactly once, unchanged; that function is simply
    stricter now (completion AND performance, not completion alone), so
    a Quest/Mission completed below its configured threshold correctly
    never reaches `ensure_access` at all, with zero new logic here. No
    second readiness/threshold gate exists anywhere in this call chain.

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

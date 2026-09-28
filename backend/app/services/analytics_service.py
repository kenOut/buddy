"""Phase 6E — Manager Analytics: a read-only aggregation layer over
existing authoritative records. No new tables, no mutation, no scoring.

Every public function here answers "what is the work revealing?" using
plain counts and ratios computed from Quest/QuestAttempt/QuestAssignment/
CapabilityEvidence/CapabilityProfile/Recommendation — the same models
every other phase already writes. Nothing is ranked or judged; see each
function's docstring for the exact definition of what it returns.

Query strategy (Part 24): a handful of grouped/bulk queries per call,
never one query per Quest or per employee. The core building blocks —
`_resolve_employee_scope`, `_resolve_quest_reach`, `_attempt_counts_by_quest`,
`_profile_counts_by_capability_level`, `_evidence_counts_by_quest_capability`,
`_all_evidence_counts_by_capability`, `_recommendations_in_scope` — each run
once per top-level call and get sliced/joined in Python afterward, so
`get_quest_analytics` costs the same number of queries whether there are
3 Quests or 300.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Capability,
    CapabilityEvidence,
    CapabilityProfile,
    Employee,
    Project,
    Quest,
    QuestAssignment,
    QuestAttempt,
    QuestCapability,
    QuestEvaluationCriterion,
    Recommendation,
)
from app.models.quest import QUEST_STATUSES
from app.models.quest_attempt import QUEST_ATTEMPT_STATUSES
from app.services import capability_gap_analysis, capability_service

_STATUS_RANK = {status: i for i, status in enumerate(QUEST_ATTEMPT_STATUSES)}

# Fixed, documented thresholds for Part 7's operational signals — small
# and deliberately simple ("do not overbuild"), never a score.
_FREQUENTLY_RECOMMENDED_THRESHOLD = 3
_HIGH_COMPLETION_ACTIVITY_THRESHOLD = 3


# =====================================================================
# Scope resolution
# =====================================================================


async def _resolve_employee_scope(db: AsyncSession, department_id: str | None) -> list[Employee]:
    stmt = select(Employee)
    if department_id:
        stmt = stmt.where(Employee.department_id == department_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _resolve_quest_reach(
    db: AsyncSession, employee_scope_ids: set[str] | None
) -> dict[str, set[str]]:
    """quest_id -> set of distinct employee_ids reachable through that
    Quest's ACTIVE assignments, resolved exactly the way
    quest_assignment_service.is_employee_eligible resolves eligibility
    per-employee — EMPLOYEE assignments map directly, DEPARTMENT/ROLE
    assignments are resolved against actual department_id/role_id
    membership. `employee_scope_ids=None` means "no department filter,
    everyone in scope"."""
    employees_result = await db.execute(select(Employee.id, Employee.department_id, Employee.role_id))
    by_department: dict[str, set[str]] = defaultdict(set)
    by_role: dict[str, set[str]] = defaultdict(set)
    all_employee_ids: set[str] = set()
    for emp_id, dept_id, role_id in employees_result.all():
        all_employee_ids.add(emp_id)
        if dept_id:
            by_department[dept_id].add(emp_id)
        if role_id:
            by_role[role_id].add(emp_id)

    in_scope = employee_scope_ids if employee_scope_ids is not None else all_employee_ids

    assignments_result = await db.execute(
        select(QuestAssignment).where(QuestAssignment.active.is_(True))
    )
    reach: dict[str, set[str]] = defaultdict(set)
    for a in assignments_result.scalars().all():
        if a.assignment_type == "EMPLOYEE" and a.employee_id:
            if a.employee_id in in_scope:
                reach[a.quest_id].add(a.employee_id)
        elif a.assignment_type == "DEPARTMENT" and a.department_id:
            reach[a.quest_id] |= by_department.get(a.department_id, set()) & in_scope
        elif a.assignment_type == "ROLE" and a.role_id:
            reach[a.quest_id] |= by_role.get(a.role_id, set()) & in_scope
    return reach


# =====================================================================
# Bulk aggregation building blocks
# =====================================================================


async def _attempt_counts_by_quest(
    db: AsyncSession, employee_scope_ids: set[str] | None
) -> dict[str, dict[str, int]]:
    """quest_id -> {status: count}, one grouped query."""
    stmt = select(QuestAttempt.quest_id, QuestAttempt.status, func.count()).group_by(
        QuestAttempt.quest_id, QuestAttempt.status
    )
    if employee_scope_ids is not None:
        stmt = stmt.where(QuestAttempt.employee_id.in_(employee_scope_ids))
    result = await db.execute(stmt)
    counts: dict[str, dict[str, int]] = defaultdict(dict)
    for quest_id, status, count in result.all():
        counts[quest_id][status] = count
    return counts


def _cumulative_attempt_stage_count(status_counts: dict[str, int], stage: str) -> int:
    """Funnel semantics (Part 5): how many attempts have REACHED AT
    LEAST this stage, using the real QuestAttempt.status rank order."""
    threshold = _STATUS_RANK[stage]
    return sum(count for status, count in status_counts.items() if _STATUS_RANK.get(status, -1) >= threshold)


async def _evidence_counts_by_quest_capability(
    db: AsyncSession, employee_scope_ids: set[str] | None
) -> dict[str, dict[str, int]]:
    """quest_id -> {capability_id: count} — QUEST-sourced
    CapabilityEvidence only (joined through QuestAttempt), one grouped
    query with a join, no per-quest fetch."""
    stmt = (
        select(QuestAttempt.quest_id, CapabilityEvidence.capability_id, func.count())
        .join(QuestAttempt, QuestAttempt.id == CapabilityEvidence.quest_attempt_id)
        .where(CapabilityEvidence.quest_attempt_id.is_not(None))
        .group_by(QuestAttempt.quest_id, CapabilityEvidence.capability_id)
    )
    if employee_scope_ids is not None:
        stmt = stmt.where(CapabilityEvidence.employee_id.in_(employee_scope_ids))
    result = await db.execute(stmt)
    counts: dict[str, dict[str, int]] = defaultdict(dict)
    for quest_id, capability_id, count in result.all():
        counts[quest_id][capability_id] = count
    return counts


async def _all_evidence_counts_by_capability(
    db: AsyncSession, employee_scope_ids: set[str] | None
) -> tuple[dict[str, int], set[str]]:
    """(capability_id -> count, distinct employee_ids with >=1 evidence
    row) — ALL evidence (Mission- and Quest-sourced), two queries
    total. Returns the actual id set (not just a count) since callers
    also need it to compute the "development history" union."""
    stmt = select(CapabilityEvidence.capability_id, func.count()).group_by(
        CapabilityEvidence.capability_id
    )
    employees_stmt = select(CapabilityEvidence.employee_id).distinct()
    if employee_scope_ids is not None:
        stmt = stmt.where(CapabilityEvidence.employee_id.in_(employee_scope_ids))
        employees_stmt = employees_stmt.where(CapabilityEvidence.employee_id.in_(employee_scope_ids))
    result = await db.execute(stmt)
    counts = {capability_id: count for capability_id, count in result.all()}
    employees_with_evidence = {row[0] for row in (await db.execute(employees_stmt)).all()}
    return counts, employees_with_evidence


async def _profile_counts_by_capability_level(
    db: AsyncSession, employee_scope_ids: set[str] | None
) -> dict[str, dict[str, int]]:
    """capability_id -> {level: employee_count}, one grouped query. A
    CapabilityProfile row only ever exists once evidence exists (see
    capability_aggregation.recompute_profile), so NOT_OBSERVED is never
    a stored level here — it's derived by the caller as
    (total_employees_in_scope - sum(these counts)) for that capability."""
    stmt = select(CapabilityProfile.capability_id, CapabilityProfile.level, func.count()).group_by(
        CapabilityProfile.capability_id, CapabilityProfile.level
    )
    if employee_scope_ids is not None:
        stmt = stmt.where(CapabilityProfile.employee_id.in_(employee_scope_ids))
    result = await db.execute(stmt)
    counts: dict[str, dict[str, int]] = defaultdict(dict)
    for capability_id, level, count in result.all():
        counts[capability_id][level] = count
    return counts


async def _recommendations_in_scope(
    db: AsyncSession, employee_scope_ids: set[str] | None
) -> list[Recommendation]:
    stmt = select(Recommendation)
    if employee_scope_ids is not None:
        stmt = stmt.where(Recommendation.employee_id.in_(employee_scope_ids))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _quest_capability_counts(db: AsyncSession) -> dict[str, int]:
    stmt = select(QuestCapability.quest_id, func.count()).group_by(QuestCapability.quest_id)
    result = await db.execute(stmt)
    return dict(result.all())


async def _quest_evaluation_criteria_counts(db: AsyncSession) -> dict[str, int]:
    stmt = select(QuestEvaluationCriterion.quest_id, func.count()).group_by(
        QuestEvaluationCriterion.quest_id
    )
    result = await db.execute(stmt)
    return dict(result.all())


# =====================================================================
# Overview (Part 4)
# =====================================================================


@dataclass
class OverviewResult:
    department_id: str | None
    published_quests: int = 0
    draft_quests: int = 0
    archived_quests: int = 0
    active_assignment_records: int = 0
    employees_reached: int = 0
    attempts_total: int = 0
    attempts_not_started: int = 0
    attempts_in_progress: int = 0
    attempts_submitted: int = 0
    attempts_evaluating: int = 0
    attempts_completed: int = 0
    employees_with_capability_evidence: int = 0
    capability_observations: int = 0
    recommendations_generated: int = 0
    employees_with_development_history: int = 0
    recent_recommendations: list[Recommendation] = field(default_factory=list)
    recent_recommendation_quest_titles: dict[str, str] = field(default_factory=dict)
    recent_recommendation_employee_names: dict[str, str] = field(default_factory=dict)


async def get_overview(db: AsyncSession, department_id: str | None) -> OverviewResult:
    employees = await _resolve_employee_scope(db, department_id)
    employee_ids = {e.id for e in employees}
    scope = employee_ids if department_id else None

    quests_stmt = select(Quest.status, func.count()).group_by(Quest.status)
    if department_id:
        # Quest.department_id — the Quest's own "home department," set at
        # authoring time (see QuestCreate). Distinct from the employee-
        # scope filter used for attempt/evidence/recommendation counts
        # below, which filters by *Employee*.department_id instead —
        # those are about which employees did the work, this is about
        # which department the Quest itself belongs to.
        quests_stmt = quests_stmt.where(Quest.department_id == department_id)
    quests_result = await db.execute(quests_stmt)
    status_counts = dict(quests_result.all())

    reach = await _resolve_quest_reach(db, scope)
    employees_reached = {emp for emps in reach.values() for emp in emps}

    active_assignment_records_stmt = select(func.count()).select_from(QuestAssignment).where(
        QuestAssignment.active.is_(True)
    )
    active_assignment_records = (await db.execute(active_assignment_records_stmt)).scalar_one()

    attempt_counts = await _attempt_counts_by_quest(db, scope)
    per_status_total: dict[str, int] = defaultdict(int)
    attempts_total = 0
    for status_counts_for_quest in attempt_counts.values():
        for status, count in status_counts_for_quest.items():
            per_status_total[status] += count
            attempts_total += count

    evidence_by_capability, employees_with_evidence = await _all_evidence_counts_by_capability(db, scope)
    capability_observations = sum(evidence_by_capability.values())

    recommendations = await _recommendations_in_scope(db, scope)

    completed_stmt = select(QuestAttempt.employee_id).where(QuestAttempt.status == "COMPLETED").distinct()
    if scope is not None:
        completed_stmt = completed_stmt.where(QuestAttempt.employee_id.in_(scope))
    employees_with_completed_quest = {row[0] for row in (await db.execute(completed_stmt)).all()}

    # "Development history" (Part 4): any employee with at least one of
    # onboarding-journey-worthy event — a completed Quest, capability
    # evidence, or a recommendation. Mirrors what Phase 6D's Development
    # Journey would show something for.
    employees_with_history = (
        employees_with_completed_quest | employees_with_evidence | {r.employee_id for r in recommendations}
    )

    recent_recommendations = sorted(recommendations, key=lambda r: r.created_at, reverse=True)[:5]
    recent_quest_titles: dict[str, str] = {}
    recent_employee_names: dict[str, str] = {}
    if recent_recommendations:
        rec_quest_ids = {r.quest_id for r in recent_recommendations}
        rec_employee_ids = {r.employee_id for r in recent_recommendations}
        titles_result = await db.execute(select(Quest.id, Quest.title).where(Quest.id.in_(rec_quest_ids)))
        recent_quest_titles = dict(titles_result.all())
        names_result = await db.execute(
            select(Employee.id, Employee.full_name).where(Employee.id.in_(rec_employee_ids))
        )
        recent_employee_names = dict(names_result.all())

    return OverviewResult(
        department_id=department_id,
        published_quests=status_counts.get("PUBLISHED", 0),
        draft_quests=status_counts.get("DRAFT", 0),
        archived_quests=status_counts.get("ARCHIVED", 0),
        active_assignment_records=active_assignment_records,
        employees_reached=len(employees_reached),
        attempts_total=attempts_total,
        attempts_not_started=per_status_total.get("NOT_STARTED", 0),
        attempts_in_progress=per_status_total.get("IN_PROGRESS", 0),
        attempts_submitted=per_status_total.get("SUBMITTED", 0),
        attempts_evaluating=per_status_total.get("EVALUATING", 0),
        attempts_completed=per_status_total.get("COMPLETED", 0),
        employees_with_capability_evidence=len(employees_with_evidence),
        capability_observations=capability_observations,
        recommendations_generated=len(recommendations),
        employees_with_development_history=len(employees_with_history),
        recent_recommendations=recent_recommendations,
        recent_recommendation_quest_titles=recent_quest_titles,
        recent_recommendation_employee_names=recent_employee_names,
    )


# =====================================================================
# Quest analytics (Part 6-7)
# =====================================================================


def _quest_signals(
    *,
    status: str,
    assigned_employees: int,
    status_counts: dict[str, int],
    evidence_count: int,
    recommendation_count: int,
) -> list[str]:
    """Deterministic operational patterns (Part 7) — never a verdict.
    Thresholds are fixed and documented here, not tuned per Quest."""
    signals: list[str] = []
    attempts_total = sum(status_counts.values())
    completed = status_counts.get("COMPLETED", 0)
    submitted_or_evaluating = status_counts.get("SUBMITTED", 0) + status_counts.get("EVALUATING", 0)

    if status == "PUBLISHED" and assigned_employees > 0 and attempts_total == 0:
        signals.append("ZERO_ATTEMPTS")
    if submitted_or_evaluating > 0 and completed == 0:
        signals.append("SUBMITTED_NOT_COMPLETED")
    if completed > 0 and evidence_count == 0:
        signals.append("NO_EVIDENCE_GENERATED")
    if status == "PUBLISHED" and recommendation_count == 0:
        signals.append("NEVER_RECOMMENDED")
    if recommendation_count >= _FREQUENTLY_RECOMMENDED_THRESHOLD:
        signals.append("FREQUENTLY_RECOMMENDED")
    if completed >= _HIGH_COMPLETION_ACTIVITY_THRESHOLD:
        signals.append("HIGH_COMPLETION_ACTIVITY")
    return signals


@dataclass
class QuestAnalyticsRow:
    quest: Quest
    project_name: str | None
    capability_count: int
    assigned_employees: int
    attempts_total: int
    attempts_completed: int
    completion_rate: float | None
    evidence_count: int
    recommendation_count: int
    signals: list[str]


async def get_quest_analytics(db: AsyncSession, department_id: str | None) -> list[QuestAnalyticsRow]:
    employees = await _resolve_employee_scope(db, department_id)
    scope = {e.id for e in employees} if department_id else None

    quests_stmt = select(Quest)
    if department_id:
        quests_stmt = quests_stmt.where(Quest.department_id == department_id)
    quests = list((await db.execute(quests_stmt)).scalars().all())

    project_ids = {q.project_id for q in quests if q.project_id}
    project_names: dict[str, str] = {}
    if project_ids:
        proj_result = await db.execute(select(Project.id, Project.name).where(Project.id.in_(project_ids)))
        project_names = dict(proj_result.all())

    reach = await _resolve_quest_reach(db, scope)
    attempt_counts = await _attempt_counts_by_quest(db, scope)
    evidence_by_quest_capability = await _evidence_counts_by_quest_capability(db, scope)
    capability_counts = await _quest_capability_counts(db)

    recommendations = await _recommendations_in_scope(db, scope)
    recommendation_counts: dict[str, int] = defaultdict(int)
    for r in recommendations:
        recommendation_counts[r.quest_id] += 1

    rows: list[QuestAnalyticsRow] = []
    for quest in quests:
        assigned = len(reach.get(quest.id, set()))
        status_counts = attempt_counts.get(quest.id, {})
        attempts_total = sum(status_counts.values())
        completed = status_counts.get("COMPLETED", 0)
        evidence_count = sum(evidence_by_quest_capability.get(quest.id, {}).values())
        recommendation_count = recommendation_counts.get(quest.id, 0)
        completion_rate = (completed / assigned) if assigned > 0 else None

        rows.append(
            QuestAnalyticsRow(
                quest=quest,
                project_name=project_names.get(quest.project_id) if quest.project_id else None,
                capability_count=capability_counts.get(quest.id, 0),
                assigned_employees=assigned,
                attempts_total=attempts_total,
                attempts_completed=completed,
                completion_rate=completion_rate,
                evidence_count=evidence_count,
                recommendation_count=recommendation_count,
                signals=_quest_signals(
                    status=quest.status,
                    assigned_employees=assigned,
                    status_counts=status_counts,
                    evidence_count=evidence_count,
                    recommendation_count=recommendation_count,
                ),
            )
        )

    rows.sort(key=lambda r: r.quest.created_at, reverse=True)
    return rows


@dataclass
class QuestDetailResult:
    quest: Quest
    project_name: str | None
    assigned_employees: int
    status_counts: dict[str, int]
    completion_rate: float | None
    evidence_count: int
    capability_breakdown: list[tuple[str, str, int]]  # (key, name, count)
    evaluation_criteria_count: int
    recommendation_count: int
    signals: list[str]


async def get_quest_detail_analytics(
    db: AsyncSession, quest_id: str, department_id: str | None
) -> QuestDetailResult | None:
    quest = await db.get(Quest, quest_id)
    if quest is None:
        return None

    employees = await _resolve_employee_scope(db, department_id)
    scope = {e.id for e in employees} if department_id else None

    project_name = None
    if quest.project_id:
        project = await db.get(Project, quest.project_id)
        project_name = project.name if project else None

    reach = await _resolve_quest_reach(db, scope)
    assigned = len(reach.get(quest_id, set()))

    attempt_counts = await _attempt_counts_by_quest(db, scope)
    status_counts = attempt_counts.get(quest_id, {})
    completed = status_counts.get("COMPLETED", 0)
    completion_rate = (completed / assigned) if assigned > 0 else None

    evidence_by_quest_capability = await _evidence_counts_by_quest_capability(db, scope)
    quest_evidence = evidence_by_quest_capability.get(quest_id, {})
    evidence_count = sum(quest_evidence.values())

    capability_breakdown: list[tuple[str, str, int]] = []
    if quest_evidence:
        cap_result = await db.execute(
            select(Capability).where(Capability.id.in_(quest_evidence.keys()))
        )
        for cap in cap_result.scalars().all():
            capability_breakdown.append((cap.key, cap.name, quest_evidence[cap.id]))
        capability_breakdown.sort(key=lambda t: t[2], reverse=True)

    criteria_counts = await _quest_evaluation_criteria_counts(db)
    evaluation_criteria_count = criteria_counts.get(quest_id, 0)

    recommendations = await _recommendations_in_scope(db, scope)
    recommendation_count = sum(1 for r in recommendations if r.quest_id == quest_id)

    return QuestDetailResult(
        quest=quest,
        project_name=project_name,
        assigned_employees=assigned,
        status_counts=status_counts,
        completion_rate=completion_rate,
        evidence_count=evidence_count,
        capability_breakdown=capability_breakdown,
        evaluation_criteria_count=evaluation_criteria_count,
        recommendation_count=recommendation_count,
        signals=_quest_signals(
            status=quest.status,
            assigned_employees=assigned,
            status_counts=status_counts,
            evidence_count=evidence_count,
            recommendation_count=recommendation_count,
        ),
    )


# =====================================================================
# Capability analytics (Part 8-9, 15)
# =====================================================================


@dataclass
class CapabilityAnalyticsRow:
    capability: Capability
    total_employees: int
    level_counts: dict[str, int]
    quests_producing_evidence: list[tuple[str, str, int]]  # (quest_id, title, count)


async def get_capability_analytics(
    db: AsyncSession, department_id: str | None
) -> list[CapabilityAnalyticsRow]:
    employees = await _resolve_employee_scope(db, department_id)
    scope = {e.id for e in employees} if department_id else None
    total_employees = len(employees)

    capabilities = list((await db.execute(select(Capability).order_by(Capability.name))).scalars().all())
    level_counts_by_capability = await _profile_counts_by_capability_level(db, scope)

    evidence_by_quest_capability = await _evidence_counts_by_quest_capability(db, scope)
    # Invert to capability_id -> [(quest_id, count), ...]
    quest_counts_by_capability: dict[str, dict[str, int]] = defaultdict(dict)
    for quest_id, cap_counts in evidence_by_quest_capability.items():
        for capability_id, count in cap_counts.items():
            quest_counts_by_capability[capability_id][quest_id] = count

    all_referenced_quest_ids = {
        qid for cap_counts in quest_counts_by_capability.values() for qid in cap_counts
    }
    quest_titles: dict[str, str] = {}
    if all_referenced_quest_ids:
        titles_result = await db.execute(
            select(Quest.id, Quest.title).where(Quest.id.in_(all_referenced_quest_ids))
        )
        quest_titles = dict(titles_result.all())

    rows: list[CapabilityAnalyticsRow] = []
    for capability in capabilities:
        quest_counts = quest_counts_by_capability.get(capability.id, {})
        quests_producing = [
            (qid, quest_titles.get(qid, "Untitled Quest"), count) for qid, count in quest_counts.items()
        ]
        quests_producing.sort(key=lambda t: t[2], reverse=True)

        rows.append(
            CapabilityAnalyticsRow(
                capability=capability,
                total_employees=total_employees,
                level_counts=level_counts_by_capability.get(capability.id, {}),
                quests_producing_evidence=quests_producing,
            )
        )
    return rows


async def get_development_signals(
    db: AsyncSession, department_id: str | None
) -> list[CapabilityAnalyticsRow]:
    """Same underlying aggregation as get_capability_analytics (Part 16
    keeps this as its own endpoint, but there's no reason to compute it
    twice) — the endpoint slices out just the DEVELOPING counts."""
    return await get_capability_analytics(db, department_id)


# =====================================================================
# Employee drill-down (Part 11-12)
# =====================================================================


@dataclass
class EmployeeAnalyticsResult:
    employee: Employee
    department_name: str | None
    role_title: str | None
    gap_analysis: capability_gap_analysis.CapabilityGapAnalysis
    evidence_counts: dict[str, int]  # capability_key -> count
    attempts: list[QuestAttempt]
    quest_titles: dict[str, str]  # quest_id -> title, for the attempts above
    latest_recommendation: Recommendation | None
    latest_recommendation_quest_title: str | None


async def get_employee_analytics(db: AsyncSession, employee_id: str) -> EmployeeAnalyticsResult | None:
    """Returns None if the employee doesn't exist. Reuses
    capability_gap_analysis.analyze_gaps (Phase 6C, unmodified) for the
    per-capability level/category classification, and
    recommendation_service.list_for_employee (Phase 6D, unmodified) for
    recommendation history — no analytics-specific re-derivation of
    either."""
    from app.services import employee_service, recommendation_service

    employee = await employee_service.get_employee(db, employee_id)
    if employee is None:
        return None

    department_name = None
    if employee.department_id:
        from app.models import Department

        department = await db.get(Department, employee.department_id)
        department_name = department.name if department else None

    role_title = None
    if employee.role_id:
        from app.models import Role

        role = await db.get(Role, employee.role_id)
        role_title = role.title if role else None

    gap_analysis = await capability_gap_analysis.analyze_gaps(db, employee_id)

    evidence_result = await db.execute(
        select(CapabilityEvidence.capability_id, func.count())
        .where(CapabilityEvidence.employee_id == employee_id)
        .group_by(CapabilityEvidence.capability_id)
    )
    evidence_counts_by_id = dict(evidence_result.all())
    # gap_analysis items are keyed by capability *key* (no id field on
    # CapabilityGapItem by design — see capability_gap_analysis.py), so
    # translate evidence_counts to the same key space here rather than
    # asking every caller to carry an id<->key lookup.
    capabilities = await capability_service.list_capabilities(db)
    key_by_id = {c.id: c.key for c in capabilities}
    evidence_counts = {
        key_by_id[cap_id]: count for cap_id, count in evidence_counts_by_id.items() if cap_id in key_by_id
    }

    attempts_result = await db.execute(
        select(QuestAttempt)
        .where(QuestAttempt.employee_id == employee_id)
        .order_by(QuestAttempt.updated_at.desc())
        .limit(10)
    )
    attempts = list(attempts_result.scalars().all())
    quest_ids = {a.quest_id for a in attempts}
    quest_titles: dict[str, str] = {}
    if quest_ids:
        titles_result = await db.execute(select(Quest.id, Quest.title).where(Quest.id.in_(quest_ids)))
        quest_titles = dict(titles_result.all())

    recommendations = await recommendation_service.list_for_employee(db, employee_id)
    latest_recommendation = recommendations[-1] if recommendations else None
    latest_recommendation_quest_title = None
    if latest_recommendation:
        rec_quest = await db.get(Quest, latest_recommendation.quest_id)
        latest_recommendation_quest_title = rec_quest.title if rec_quest else "A Quest that's no longer available"

    return EmployeeAnalyticsResult(
        employee=employee,
        department_name=department_name,
        role_title=role_title,
        gap_analysis=gap_analysis,
        evidence_counts=evidence_counts,
        attempts=attempts,
        quest_titles=quest_titles,
        latest_recommendation=latest_recommendation,
        latest_recommendation_quest_title=latest_recommendation_quest_title,
    )


# =====================================================================
# Capability -> employees drill-down (Part 11)
# =====================================================================


@dataclass
class CapabilityEmployeeRow:
    employee: Employee
    department_name: str | None
    role_title: str | None
    level: str
    evidence_count: int


async def get_capability_employees(
    db: AsyncSession, capability_id: str, category: str, department_id: str | None
) -> list[CapabilityEmployeeRow] | None:
    """The drill-down behind an aggregate count like "6 employees have
    Documentation classified as a development area" (Part 9) — clicking
    that number needs to reveal who, per Part 11. `category` is one of
    capability_gap_analysis's four categories (STRENGTH/CAPABLE/
    DEVELOPMENT_AREA/UNOBSERVED); returns None only if the capability_id
    doesn't exist."""
    from app.models import Department, Role

    capability = await db.get(Capability, capability_id)
    if capability is None:
        return None

    employees = await _resolve_employee_scope(db, department_id)
    department_ids = {e.department_id for e in employees if e.department_id}
    role_ids = {e.role_id for e in employees if e.role_id}
    department_names: dict[str, str] = {}
    role_titles: dict[str, str] = {}
    if department_ids:
        dept_result = await db.execute(select(Department.id, Department.name).where(Department.id.in_(department_ids)))
        department_names = dict(dept_result.all())
    if role_ids:
        role_result = await db.execute(select(Role.id, Role.title).where(Role.id.in_(role_ids)))
        role_titles = dict(role_result.all())

    profiles_result = await db.execute(
        select(CapabilityProfile).where(CapabilityProfile.capability_id == capability_id)
    )
    profile_by_employee = {p.employee_id: p for p in profiles_result.scalars().all()}

    evidence_result = await db.execute(
        select(CapabilityEvidence.employee_id, func.count())
        .where(CapabilityEvidence.capability_id == capability_id)
        .group_by(CapabilityEvidence.employee_id)
    )
    evidence_counts = dict(evidence_result.all())

    level_for_category = {
        "STRENGTH": "STRONG",
        "CAPABLE": "CAPABLE",
        "DEVELOPMENT_AREA": "DEVELOPING",
        "UNOBSERVED": "NOT_OBSERVED",
    }.get(category)

    rows: list[CapabilityEmployeeRow] = []
    for employee in employees:
        profile = profile_by_employee.get(employee.id)
        level = profile.level if profile else "NOT_OBSERVED"
        if level != level_for_category:
            continue
        rows.append(
            CapabilityEmployeeRow(
                employee=employee,
                department_name=department_names.get(employee.department_id) if employee.department_id else None,
                role_title=role_titles.get(employee.role_id) if employee.role_id else None,
                level=level,
                evidence_count=evidence_counts.get(employee.id, 0),
            )
        )
    rows.sort(key=lambda r: r.employee.full_name)
    return rows

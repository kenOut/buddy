"""Phase 6B — Quest Quality Validation.

Answers "is this actually a meaningful, attemptable, evaluable work
challenge?" — a strictly stronger successor to Stage 6A's
publish-readiness (challenge/capability/assignment only). Stage 6A's
`quest_service.get_publish_readiness`/`PublishReadiness` dataclasses are
retired in favor of this module; `quest_service.publish_quest` and the
`GET /quests/{id}/publish-readiness` endpoint both call `validate_quest`
below rather than trusting each other or the frontend.

`section` values deliberately match the Manager Quest Builder's six tab
keys 1:1 (see frontend/src/components/admin/quest-builder/BuilderNav.tsx)
so the frontend can jump straight to the right tab from a failing check
with no translation table.
"""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Quest, QuestEvaluationCriterion
from app.services import quest_quality_config

ERROR = "ERROR"
WARNING = "WARNING"


@dataclass
class QualityCheck:
    code: str
    severity: str  # ERROR | WARNING
    message: str
    section: str
    satisfied: bool


@dataclass
class QuestQualityValidation:
    ready: bool
    errors: list[QualityCheck] = field(default_factory=list)
    warnings: list[QualityCheck] = field(default_factory=list)
    checks: list[QualityCheck] = field(default_factory=list)


def _criterion_is_well_formed(criterion: QuestEvaluationCriterion) -> bool:
    """Mirrors Stage 4's per-type minimum: DETERMINISTIC needs a real
    expected answer, BEHAVIORAL needs a real expected behavior,
    QUALITATIVE needs some evaluator guidance (a description or a
    reference solution — either is acceptable, not both)."""
    if criterion.criterion_type == "DETERMINISTIC":
        return bool(criterion.expected_answer and criterion.expected_answer.strip())
    if criterion.criterion_type == "BEHAVIORAL":
        return bool(criterion.expected_behavior and criterion.expected_behavior.strip())
    if criterion.criterion_type == "QUALITATIVE":
        return bool(
            (criterion.reference_solution and criterion.reference_solution.strip())
            or (criterion.description and criterion.description.strip())
        )
    return True


async def validate_quest(db: AsyncSession, quest: Quest) -> QuestQualityValidation:
    # Local imports: avoids a cycle with quest_service, which calls into
    # this module (same pattern as Stage 6A's get_publish_readiness).
    from app.services import (
        quest_assignment_service,
        quest_capability_service,
        quest_evaluation_criterion_service,
        quest_evidence_service,
        quest_task_service,
    )

    tasks = await quest_task_service.list_tasks(db, quest.id)
    evidence = await quest_evidence_service.list_evidence(db, quest.id)
    criteria = await quest_evaluation_criterion_service.list_criteria(db, quest.id)
    capabilities = await quest_capability_service.list_mappings(db, quest.id)
    has_assignment = await quest_assignment_service.has_active_assignment(db, quest.id)

    requirements = quest_quality_config.get_requirements(quest.quest_type)
    checks: list[QualityCheck] = []

    # ---- Challenge ----
    challenge_defined = bool(quest.description and quest.description.strip())
    checks.append(
        QualityCheck(
            code="MISSING_CHALLENGE",
            severity=ERROR,
            message="Describe the challenge before publishing — this is the only thing an "
            "employee sees before they start.",
            section="challenge",
            satisfied=challenge_defined,
        )
    )

    # ---- Task (generic existence + type-specific requirement, one check) ----
    if not tasks:
        task_satisfied = False
    elif requirements.required_task_types:
        task_satisfied = any(t.task_type in requirements.required_task_types for t in tasks)
    else:
        task_satisfied = True
    checks.append(
        QualityCheck(
            code=requirements.task_type_check_code,
            severity=ERROR,
            message=requirements.task_type_check_message,
            section="work-evidence",
            satisfied=task_satisfied,
        )
    )

    # ---- Evidence ----
    evidence_present = len(evidence) > 0
    checks.append(
        QualityCheck(
            code="MISSING_EVIDENCE",
            severity=ERROR if requirements.requires_evidence else WARNING,
            message=(
                f"{requirements.quest_type.title()} quests require at least one evidence item "
                "for the employee to investigate."
                if requirements.requires_evidence
                else "Evidence isn't required for this quest type, but adding some helps the "
                "employee ground their work in something concrete."
            ),
            section="work-evidence",
            satisfied=evidence_present,
        )
    )

    # ---- Evaluation: exists at all ----
    evaluation_defined = len(criteria) > 0
    checks.append(
        QualityCheck(
            code="MISSING_EVALUATION",
            severity=ERROR,
            message="Add at least one evaluation criterion so Buddy can assess submissions.",
            section="evaluation",
            satisfied=evaluation_defined,
        )
    )

    # ---- Evaluation: content quality of whatever criteria exist ----
    if criteria:
        all_well_formed = all(_criterion_is_well_formed(c) for c in criteria)
        checks.append(
            QualityCheck(
                code="INVALID_EVALUATION_CRITERION",
                severity=ERROR,
                message=(
                    "One or more evaluation criteria are missing the content needed to actually "
                    "score a submission — a Deterministic criterion needs an expected answer, a "
                    "Behavioral criterion needs an expected behavior, and a Qualitative criterion "
                    "needs a description or reference solution."
                ),
                section="evaluation",
                satisfied=all_well_formed,
            )
        )

    # ---- Expected outcome (BUILD / CREATE_SOLUTION only) ----
    if requirements.requires_expected_outcome:
        has_outcome = any(_criterion_is_well_formed(c) for c in criteria)
        checks.append(
            QualityCheck(
                code="MISSING_EXPECTED_OUTCOME",
                severity=ERROR,
                message=(
                    f"{requirements.quest_type.title().replace('_', ' ')} quests need at least "
                    "one evaluation criterion that spells out what a good outcome looks like."
                ),
                section="evaluation",
                satisfied=has_outcome,
            )
        )

    # ---- Capabilities ----
    checks.append(
        QualityCheck(
            code="MISSING_CAPABILITY",
            severity=ERROR,
            message="Map at least one capability this quest demonstrates.",
            section="capabilities",
            satisfied=len(capabilities) > 0,
        )
    )

    # ---- Assignment ----
    checks.append(
        QualityCheck(
            code="MISSING_ASSIGNMENT",
            severity=ERROR,
            message="Add an active assignment — assign this quest to at least one employee, "
            "department, or role before publishing.",
            section="assign-publish",
            satisfied=has_assignment,
        )
    )

    errors = [c for c in checks if c.severity == ERROR and not c.satisfied]
    warnings = [c for c in checks if c.severity == WARNING and not c.satisfied]
    return QuestQualityValidation(ready=len(errors) == 0, errors=errors, warnings=warnings, checks=checks)

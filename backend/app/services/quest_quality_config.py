"""Phase 6B — centralized Quest Type requirement table.

Single source of truth for "what does a minimally meaningful Quest of
this type need?" — consumed only by quest_quality_service.py. Nothing
elsewhere should branch on quest_type for validation purposes; add a
new QuestTypeRequirements entry here instead of a conditional at a call
site.

Uses the actual QUEST_TYPES/TASK_TYPES values already defined on the
models (app/models/quest.py, app/models/quest_task.py) — no parallel
enum is introduced.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class QuestTypeRequirements:
    quest_type: str

    # Evidence: some quest types are fundamentally about examining
    # material (investigation/analysis/troubleshooting/fixing a defect)
    # and cannot be meaningfully attempted without it. For those,
    # missing evidence is an ERROR; for the rest it's a WARNING (still
    # useful almost always, never strictly required).
    requires_evidence: bool

    # A quest type may require at least one task of a specific
    # task_type (e.g. DESIGN needs a task typed DESIGN). Empty tuple
    # means "any task satisfies the generic requirement" — no
    # type-specific task check is run.
    required_task_types: tuple[str, ...]
    task_type_check_code: str
    task_type_check_message: str

    # BUILD/CREATE_SOLUTION quests are specifically about producing a
    # result — beyond "an evaluation criterion exists", at least one
    # criterion must actually carry usable expected-outcome content
    # (see quest_quality_service._criterion_is_well_formed).
    requires_expected_outcome: bool = False


_REQUIREMENTS: dict[str, QuestTypeRequirements] = {
    "TROUBLESHOOT": QuestTypeRequirements(
        quest_type="TROUBLESHOOT",
        requires_evidence=True,
        required_task_types=("INVESTIGATE",),
        task_type_check_code="MISSING_INVESTIGATION_TASK",
        task_type_check_message=(
            "Troubleshooting quests need at least one investigation-oriented task "
            "(task type: Investigate)."
        ),
    ),
    "INVESTIGATE": QuestTypeRequirements(
        quest_type="INVESTIGATE",
        requires_evidence=True,
        required_task_types=("INVESTIGATE",),
        task_type_check_code="MISSING_INVESTIGATION_TASK",
        task_type_check_message=(
            "Investigate quests need at least one investigation-oriented task "
            "(task type: Investigate)."
        ),
    ),
    "ANALYZE": QuestTypeRequirements(
        quest_type="ANALYZE",
        requires_evidence=True,
        required_task_types=("ANALYZE",),
        task_type_check_code="MISSING_ANALYSIS_TASK",
        task_type_check_message="Analyze quests need at least one analysis task (task type: Analyze).",
    ),
    "FIX": QuestTypeRequirements(
        quest_type="FIX",
        requires_evidence=True,
        required_task_types=("FIX",),
        task_type_check_code="MISSING_TASK",
        task_type_check_message=(
            "Fix quests need at least one task describing the fix (task type: Fix)."
        ),
    ),
    "DESIGN": QuestTypeRequirements(
        quest_type="DESIGN",
        requires_evidence=False,
        required_task_types=("DESIGN",),
        task_type_check_code="MISSING_DESIGN_TASK",
        task_type_check_message="Design quests need at least one design task (task type: Design).",
    ),
    "BUILD": QuestTypeRequirements(
        quest_type="BUILD",
        requires_evidence=False,
        required_task_types=("BUILD", "CREATE"),
        task_type_check_code="MISSING_TASK",
        task_type_check_message=(
            "Build quests need at least one implementation task (task type: Build or Create)."
        ),
        requires_expected_outcome=True,
    ),
    "CREATE_SOLUTION": QuestTypeRequirements(
        quest_type="CREATE_SOLUTION",
        requires_evidence=False,
        required_task_types=("CREATE", "BUILD"),
        task_type_check_code="MISSING_SOLUTION_TASK",
        task_type_check_message=(
            "Solution quests need at least one solution task (task type: Create or Build)."
        ),
        requires_expected_outcome=True,
    ),
    "OTHER": QuestTypeRequirements(
        quest_type="OTHER",
        requires_evidence=False,
        required_task_types=(),
        task_type_check_code="MISSING_TASK",
        task_type_check_message="Add at least one task describing what the employee should do.",
    ),
}


def get_requirements(quest_type: str) -> QuestTypeRequirements:
    """Falls back to OTHER's generic minimum for any quest_type not
    explicitly listed above, so a new QUEST_TYPES value never crashes
    validation — it just gets the baseline until someone defines
    something more specific for it here."""
    return _REQUIREMENTS.get(quest_type, _REQUIREMENTS["OTHER"])

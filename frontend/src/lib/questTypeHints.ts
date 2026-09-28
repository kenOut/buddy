import type { QuestType } from "@/lib/types";

/** Phase 6B — purely descriptive per-type authoring hints for the
 * Manager Quest Builder. Mirrors the *shape* of the backend's
 * quest_quality_config.py but carries no validation logic of its own —
 * the backend (quest_quality_service.py) remains the sole source of
 * truth for what's actually required. This module only decides what
 * helper text to show; getPublishReadiness/publishQuest decide what's
 * actually blocking. */
export interface QuestTypeHint {
  label: string;
  taskHint: string;
  evidenceHint: string;
  evidenceRequired: boolean;
  evaluationHint: string;
}

const HINTS: Record<QuestType, QuestTypeHint> = {
  TROUBLESHOOT: {
    label: "Troubleshoot",
    taskHint: "Add at least one Investigate-typed task — troubleshooting starts with finding the cause.",
    evidenceHint: "Required. Give the employee something real to investigate (logs, metrics, alerts).",
    evidenceRequired: true,
    evaluationHint: "Define the root cause / proposed fix you expect to see.",
  },
  INVESTIGATE: {
    label: "Investigate",
    taskHint: "Add at least one Investigate-typed task.",
    evidenceHint: "Required. This quest type is about examining real material.",
    evidenceRequired: true,
    evaluationHint: "Define what a correct finding looks like.",
  },
  ANALYZE: {
    label: "Analyze",
    taskHint: "Add at least one Analyze-typed task.",
    evidenceHint: "Required. Provide the data or dataset the employee should analyze.",
    evidenceRequired: true,
    evaluationHint: "Define what a sound analysis should conclude.",
  },
  FIX: {
    label: "Fix",
    taskHint: "Add at least one Fix-typed task describing what needs fixing.",
    evidenceHint: "Required. Provide reproduction steps or evidence of the defect.",
    evidenceRequired: true,
    evaluationHint: "Define how you'll recognize a correct fix.",
  },
  BUILD: {
    label: "Build",
    taskHint: "Add at least one Build-typed (or Create-typed) implementation task.",
    evidenceHint: "Optional, but requirements or reference material can help.",
    evidenceRequired: false,
    evaluationHint: "Spell out the expected outcome — what does a working result look like?",
  },
  DESIGN: {
    label: "Design",
    taskHint: "Add at least one Design-typed task.",
    evidenceHint: "Optional — constraints can also live in the challenge description.",
    evidenceRequired: false,
    evaluationHint: "Define the trade-offs or constraints a good design should address.",
  },
  CREATE_SOLUTION: {
    label: "Create a solution",
    taskHint: "Add at least one Create-typed (or Build-typed) solution task.",
    evidenceHint: "Optional.",
    evidenceRequired: false,
    evaluationHint: "Spell out the expected outcome the solution should achieve.",
  },
  OTHER: {
    label: "Other",
    taskHint: "Add at least one task describing what the employee should do.",
    evidenceHint: "Optional.",
    evidenceRequired: false,
    evaluationHint: "Define what a good submission looks like.",
  },
};

export function getQuestTypeHint(questType: QuestType): QuestTypeHint {
  return HINTS[questType] ?? HINTS.OTHER;
}

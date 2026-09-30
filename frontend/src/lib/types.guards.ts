import type {
  EmployeeQuest, QuestTaskItem, QuestEvidenceItem,
  QuestEvaluationResult, DevelopmentJourneyItem,
} from "./types";

type AssertNever<T extends never> = T;

type CriteriaLeak = "evaluation_criteria" | "expected_answer" | "expected_behavior" | "reference_solution";
type WorkspaceLeak = "external_ref" | "provider" | "provider_ref" | "last_error" | "attempt_count";

export type _Guards = [
  AssertNever<Extract<keyof EmployeeQuest, CriteriaLeak>>,
  AssertNever<Extract<keyof QuestTaskItem, CriteriaLeak>>,
  AssertNever<Extract<keyof QuestEvidenceItem, CriteriaLeak>>,
  AssertNever<Extract<keyof QuestEvaluationResult, CriteriaLeak>>,
  AssertNever<Extract<keyof DevelopmentJourneyItem, WorkspaceLeak>>,
];

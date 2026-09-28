import { api } from "@/lib/api";
import type { EmployeeQuest, QuestAttempt, QuestEligibility, QuestEvaluationResult } from "@/lib/types";

export function getQuestEligibility(questId: string, employeeId: string) {
  return api.get<QuestEligibility>(
    `/quests/${encodeURIComponent(questId)}/eligibility/${encodeURIComponent(employeeId)}`
  );
}

export function getEmployeeQuest(questId: string, employeeId: string) {
  return api.get<EmployeeQuest>(
    `/quests/${encodeURIComponent(questId)}/employee?employee_id=${encodeURIComponent(employeeId)}`
  );
}

export function createQuestAttempt(questId: string, employeeId: string) {
  return api.post<QuestAttempt>("/quest-attempts", { quest_id: questId, employee_id: employeeId });
}

export function getQuestAttempt(attemptId: string, employeeId: string) {
  return api.get<QuestAttempt>(
    `/quest-attempts/${encodeURIComponent(attemptId)}?employee_id=${encodeURIComponent(employeeId)}`
  );
}

export interface QuestAttemptAutosavePayload {
  employee_id: string;
  findings?: string;
  reasoning?: string;
  solution?: string;
  completed_task_ids?: string[];
  workspace?: { type: string; payload: Record<string, unknown> };
}

export function updateQuestAttempt(attemptId: string, payload: QuestAttemptAutosavePayload) {
  return api.patch<QuestAttempt>(`/quest-attempts/${encodeURIComponent(attemptId)}`, payload);
}

export function submitQuestAttempt(attemptId: string, employeeId: string) {
  return api.post<QuestAttempt>(`/quest-attempts/${encodeURIComponent(attemptId)}/submit`, {
    employee_id: employeeId,
  });
}

export function evaluateQuestAttempt(attemptId: string, employeeId: string) {
  return api.post<QuestEvaluationResult | null>(
    `/quest-attempts/${encodeURIComponent(attemptId)}/evaluate`,
    { employee_id: employeeId }
  );
}

export function getQuestAttemptEvaluation(attemptId: string, employeeId: string) {
  return api.get<QuestEvaluationResult | null>(
    `/quest-attempts/${encodeURIComponent(attemptId)}/evaluation?employee_id=${encodeURIComponent(employeeId)}`
  );
}

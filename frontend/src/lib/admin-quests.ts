/** Manager-facing Quest API wrapper — deliberately separate from
 * lib/quests.ts (the employee-facing module). Every call here can reach
 * manager/internal data (QuestDetail, evaluation criteria with hidden
 * fields); nothing in lib/quests.ts should ever import from this file,
 * and this file should never be imported from an employee-facing route. */
import { api } from "@/lib/api";
import type {
  Quest,
  QuestAssignment,
  QuestAssignmentInput,
  QuestCapabilityInput,
  QuestCapabilityMapping,
  QuestCreateInput,
  QuestDetail,
  QuestEvaluationCriterion,
  QuestEvaluationCriterionInput,
  QuestEvidenceInput,
  QuestEvidenceItem,
  QuestQualityValidation,
  QuestTaskInput,
  QuestTaskItem,
  QuestUpdateInput,
} from "@/lib/types";

const q = (id: string) => encodeURIComponent(id);

// ---- Quest ----

export function listQuests(departmentId?: string) {
  const query = departmentId ? `?department_id=${q(departmentId)}` : "";
  return api.get<Quest[]>(`/quests${query}`);
}

export function createQuest(payload: QuestCreateInput) {
  return api.post<Quest>("/quests", payload);
}

export function getQuest(questId: string) {
  return api.get<Quest>(`/quests/${q(questId)}`);
}

export function getQuestDetail(questId: string) {
  return api.get<QuestDetail>(`/quests/${q(questId)}/detail`);
}

export function updateQuest(questId: string, payload: QuestUpdateInput) {
  return api.patch<Quest>(`/quests/${q(questId)}`, payload);
}

export function getPublishReadiness(questId: string) {
  return api.get<QuestQualityValidation>(`/quests/${q(questId)}/publish-readiness`);
}

export function publishQuest(questId: string) {
  return api.post<Quest>(`/quests/${q(questId)}/publish`);
}

export function archiveQuest(questId: string) {
  return api.post<Quest>(`/quests/${q(questId)}/archive`);
}

// ---- Tasks ----

export function createQuestTask(questId: string, payload: QuestTaskInput) {
  return api.post<QuestTaskItem>(`/quests/${q(questId)}/tasks`, payload);
}

export function updateQuestTask(questId: string, taskId: string, payload: Partial<QuestTaskInput>) {
  return api.patch<QuestTaskItem>(`/quests/${q(questId)}/tasks/${q(taskId)}`, payload);
}

export function deleteQuestTask(questId: string, taskId: string) {
  return api.delete<void>(`/quests/${q(questId)}/tasks/${q(taskId)}`);
}

// ---- Evidence ----

export function createQuestEvidence(questId: string, payload: QuestEvidenceInput) {
  return api.post<QuestEvidenceItem>(`/quests/${q(questId)}/evidence`, payload);
}

export function updateQuestEvidence(
  questId: string,
  evidenceId: string,
  payload: Partial<QuestEvidenceInput>
) {
  return api.patch<QuestEvidenceItem>(`/quests/${q(questId)}/evidence/${q(evidenceId)}`, payload);
}

export function deleteQuestEvidence(questId: string, evidenceId: string) {
  return api.delete<void>(`/quests/${q(questId)}/evidence/${q(evidenceId)}`);
}

// ---- Evaluation criteria ----

export function createQuestCriterion(questId: string, payload: QuestEvaluationCriterionInput) {
  return api.post<QuestEvaluationCriterion>(`/quests/${q(questId)}/evaluation-criteria`, payload);
}

export function updateQuestCriterion(
  questId: string,
  criterionId: string,
  payload: Partial<QuestEvaluationCriterionInput>
) {
  return api.patch<QuestEvaluationCriterion>(
    `/quests/${q(questId)}/evaluation-criteria/${q(criterionId)}`,
    payload
  );
}

export function deleteQuestCriterion(questId: string, criterionId: string) {
  return api.delete<void>(`/quests/${q(questId)}/evaluation-criteria/${q(criterionId)}`);
}

// ---- Capabilities ----

export function mapQuestCapability(questId: string, payload: QuestCapabilityInput) {
  return api.post<QuestCapabilityMapping>(`/quests/${q(questId)}/capabilities`, payload);
}

export function unmapQuestCapability(questId: string, capabilityId: string) {
  return api.delete<void>(`/quests/${q(questId)}/capabilities/${q(capabilityId)}`);
}

// ---- Assignments ----

export function listQuestAssignments(questId: string) {
  return api.get<QuestAssignment[]>(`/quests/${q(questId)}/assignments`);
}

export function createQuestAssignment(questId: string, payload: QuestAssignmentInput) {
  return api.post<QuestAssignment>(`/quests/${q(questId)}/assignments`, payload);
}

export function updateQuestAssignment(questId: string, assignmentId: string, active: boolean) {
  return api.patch<QuestAssignment>(`/quests/${q(questId)}/assignments/${q(assignmentId)}`, {
    active,
  });
}

export function deleteQuestAssignment(questId: string, assignmentId: string) {
  return api.delete<void>(`/quests/${q(questId)}/assignments/${q(assignmentId)}`);
}

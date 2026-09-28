import { api } from "@/lib/api";
import type { MissionAttempt, MissionQuiz, MissionScenario } from "@/lib/types";

export function getMissionScenario(missionId: string, employeeId: string) {
  return api.get<MissionScenario>(
    `/missions/${encodeURIComponent(missionId)}/scenario?employee_id=${encodeURIComponent(employeeId)}`
  );
}

export function getMissionQuiz(missionId: string, employeeId: string) {
  return api.get<MissionQuiz>(
    `/missions/${encodeURIComponent(missionId)}/quiz?employee_id=${encodeURIComponent(employeeId)}`
  );
}

export function getMissionAttempt(missionId: string, employeeId: string) {
  return api.get<MissionAttempt>(
    `/mission-attempts?mission_id=${encodeURIComponent(missionId)}&employee_id=${encodeURIComponent(employeeId)}`
  );
}

export function createMissionAttempt(missionId: string, employeeId: string) {
  return api.post<MissionAttempt>("/mission-attempts", {
    mission_id: missionId,
    employee_id: employeeId,
  });
}

export interface MissionAttemptPatch {
  affected_service?: string | null;
  likely_cause?: string | null;
  reasoning?: string | null;
  evidence_viewed?: string[];
  quiz_answers?: Record<string, string>;
}

export function updateMissionAttempt(attemptId: string, patch: MissionAttemptPatch) {
  return api.patch<MissionAttempt>(`/mission-attempts/${attemptId}`, patch);
}

/** Which fields are required depends on the Mission's own workspace_type
 * (investigation/quiz/reflection) — enforced server-side in
 * mission_attempt_service.submit_attempt, not by this type, which just
 * mirrors the backend's own permissive MissionAttemptSubmit schema. */
export interface MissionAttemptSubmission {
  employee_id: string;
  affected_service?: string;
  likely_cause?: string;
  reasoning?: string;
  evidence_viewed?: string[];
  quiz_answers?: Record<string, string>;
}

export function submitMissionAttempt(attemptId: string, payload: MissionAttemptSubmission) {
  return api.post<MissionAttempt>(`/mission-attempts/${attemptId}/submit`, payload);
}

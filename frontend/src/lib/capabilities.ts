import { api } from "@/lib/api";
import type {
  Capability,
  CapabilityEvaluation,
  CapabilityEvidence,
  CapabilityProfile,
  EmployeeReadinessSummary,
  NextMissionResponse,
  NextQuestResponse,
} from "@/lib/types";

export function listCapabilities() {
  return api.get<Capability[]>("/capabilities");
}

export function getEmployeeCapabilities(employeeId: string) {
  return api.get<CapabilityProfile[]>(`/employees/${encodeURIComponent(employeeId)}/capabilities`);
}

export function getEmployeeCapabilityEvidence(employeeId: string, capabilityId?: string) {
  const query = capabilityId ? `?capability_id=${encodeURIComponent(capabilityId)}` : "";
  return api.get<CapabilityEvidence[]>(
    `/employees/${encodeURIComponent(employeeId)}/capabilities/evidence${query}`
  );
}

export function getMissionAttemptEvaluation(attemptId: string, employeeId: string) {
  return api.get<CapabilityEvaluation | null>(
    `/mission-attempts/${encodeURIComponent(attemptId)}/evaluation?employee_id=${encodeURIComponent(employeeId)}`
  );
}

export function evaluateMissionAttempt(attemptId: string, employeeId: string) {
  return api.post<CapabilityEvaluation>(`/mission-attempts/${encodeURIComponent(attemptId)}/evaluate`, {
    employee_id: employeeId,
  });
}

export function getNextMission(employeeId: string) {
  return api.get<NextMissionResponse>(`/employees/${encodeURIComponent(employeeId)}/next-mission`);
}

export function getNextQuest(employeeId: string) {
  return api.get<NextQuestResponse>(`/employees/${encodeURIComponent(employeeId)}/next-quest`);
}

export function getReadinessSummary(employeeId: string) {
  return api.get<EmployeeReadinessSummary>(
    `/employees/${encodeURIComponent(employeeId)}/readiness-summary`
  );
}

import { api } from "@/lib/api";
import type {
  AnalyticsCapabilitiesResponse,
  AnalyticsDevelopmentSignalsResponse,
  AnalyticsOverview,
  AnalyticsQuestsResponse,
  CapabilityEmployeesResponse,
  CapabilityGapCategory,
  EmployeeAnalytics,
  QuestDetailAnalytics,
} from "@/lib/types";

/** Phase 6E — manager-only, read-only analytics. Deliberately a
 * separate module from lib/quests.ts / lib/capabilities.ts (the
 * employee-facing ones) — this is never imported from an
 * employee-facing route. */

function query(departmentId?: string | null): string {
  return departmentId ? `?department_id=${encodeURIComponent(departmentId)}` : "";
}

export function getAnalyticsOverview(departmentId?: string | null) {
  return api.get<AnalyticsOverview>(`/analytics/overview${query(departmentId)}`);
}

export function getQuestAnalytics(departmentId?: string | null) {
  return api.get<AnalyticsQuestsResponse>(`/analytics/quests${query(departmentId)}`);
}

export function getQuestDetailAnalytics(questId: string, departmentId?: string | null) {
  return api.get<QuestDetailAnalytics>(
    `/analytics/quests/${encodeURIComponent(questId)}${query(departmentId)}`
  );
}

export function getCapabilityAnalytics(departmentId?: string | null) {
  return api.get<AnalyticsCapabilitiesResponse>(`/analytics/capabilities${query(departmentId)}`);
}

export function getDevelopmentSignals(departmentId?: string | null) {
  return api.get<AnalyticsDevelopmentSignalsResponse>(`/analytics/development-signals${query(departmentId)}`);
}

export function getEmployeeAnalytics(employeeId: string) {
  return api.get<EmployeeAnalytics>(`/analytics/employees/${encodeURIComponent(employeeId)}`);
}

export function getCapabilityEmployees(
  capabilityId: string,
  category: CapabilityGapCategory,
  departmentId?: string | null
) {
  const params = new URLSearchParams({ category });
  if (departmentId) params.set("department_id", departmentId);
  return api.get<CapabilityEmployeesResponse>(
    `/analytics/capabilities/${encodeURIComponent(capabilityId)}/employees?${params.toString()}`
  );
}

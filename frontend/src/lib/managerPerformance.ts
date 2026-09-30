import { api } from "@/lib/api";
import type { ManagerEmployeePerformanceResponse } from "@/lib/types";

/** Admin-authenticated — this call rides the same cookie every other
 * `/employees/*` admin request already uses (see employees.router's
 * router-level require_admin_session in api/v1/router.py), never an
 * employee session. */
export function getEmployeePerformance(employeeId: string) {
  return api.get<ManagerEmployeePerformanceResponse>(
    `/employees/${encodeURIComponent(employeeId)}/performance`
  );
}

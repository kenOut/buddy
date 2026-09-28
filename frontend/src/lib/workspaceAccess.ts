import { api } from "@/lib/api";
import type { EmployeeWorkspaceAccess } from "@/lib/types";

/** Phase 8E — employee-facing, read-only. Never triggers a grant; just
 * reads whatever the backend already decided (see the endpoint's own
 * docstring, GET /employees/{employee_id}/workspace-access). */
export function getWorkspaceAccess(employeeId: string): Promise<EmployeeWorkspaceAccess> {
  return api.get<EmployeeWorkspaceAccess>(`/employees/${employeeId}/workspace-access`);
}

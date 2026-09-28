import { api } from "@/lib/api";
import type { DevelopmentJourneyResponse } from "@/lib/types";

export function getDevelopmentJourney(employeeId: string) {
  return api.get<DevelopmentJourneyResponse>(
    `/employees/${encodeURIComponent(employeeId)}/development-journey`
  );
}

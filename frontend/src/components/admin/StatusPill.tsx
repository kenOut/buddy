import { Badge } from "@/components/ui/Badge";
import type { EmployeeStatus, SessionStatus } from "@/lib/types";

const employeeTone: Record<EmployeeStatus, "neutral" | "info" | "success" | "coral"> = {
  invited: "neutral",
  onboarding: "info",
  active: "success",
  inactive: "coral",
};

const sessionTone: Record<SessionStatus, "neutral" | "info" | "success"> = {
  not_started: "neutral",
  in_progress: "info",
  completed: "success",
};

export function EmployeeStatusPill({ status }: { status: EmployeeStatus }) {
  return <Badge tone={employeeTone[status]}>{status}</Badge>;
}

export function SessionStatusPill({ status }: { status: SessionStatus }) {
  return <Badge tone={sessionTone[status]}>{status.replace("_", " ")}</Badge>;
}

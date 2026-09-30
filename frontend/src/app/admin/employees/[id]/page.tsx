import Link from "next/link";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";

import { PersonCard } from "@/components/onboarding/PersonCard";
import { EmployeeAvatarUpload } from "@/components/admin/EmployeeAvatarUpload";
import { EmployeeStatusPill, SessionStatusPill } from "@/components/admin/StatusPill";
import { EmployeeDevelopmentSnapshot } from "@/components/analytics/EmployeeDevelopmentSnapshot";
import { ManagerPerformanceSection } from "@/components/admin/ManagerPerformanceSection";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import type { OnboardingBundle } from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

async function getBundle(employeeId: string): Promise<OnboardingBundle | null> {
  // P1 — Identity & Invitation Foundation: GET /onboarding/bundle/{id}
  // is now admin-gated server-side. This is a Server Component fetch,
  // so it never carries the browser's cookies automatically the way
  // `credentials: "include"` does client-side — the admin's own session
  // cookie has to be forwarded explicitly, or this (already-working,
  // already-authenticated-in-the-browser) admin page would start
  // getting 401s once the backend route stopped being open to everyone.
  const cookieStore = await cookies();
  const cookieHeader = cookieStore.getAll().map((c) => `${c.name}=${c.value}`).join("; ");

  const res = await fetch(`${API_BASE_URL}/onboarding/bundle/${employeeId}`, {
    cache: "no-store",
    headers: { Cookie: cookieHeader },
  });
  if (res.status === 404 || res.status === 401) return null;
  if (!res.ok) throw new Error("Failed to load employee");
  return res.json();
}

export default async function EmployeeDetailPage({
  params,
}: PageProps<"/admin/employees/[id]">) {
  const { id } = await params;
  const bundle = await getBundle(id);
  if (!bundle) notFound();

  const { employee, department, role, manager, supervisor, session, mission_assignments } = bundle;
  const completed = mission_assignments.filter((a) => a.status === "completed").length;

  return (
    <div className="space-y-6">
      <Link href="/admin/employees" className="text-sm text-buddy-muted hover:text-foreground">
        ← Back to employees
      </Link>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <EmployeeAvatarUpload employee={employee} />
          <div>
            <h1 className="text-2xl font-semibold">{employee.full_name}</h1>
            <p className="text-sm text-buddy-muted">
              {role?.title ?? employee.job_title} · {department?.name ?? "No department"}
            </p>
          </div>
        </div>
        <EmployeeStatusPill status={employee.status} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card>
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-buddy-muted">
            Onboarding session
          </p>
          {session ? (
            <div className="space-y-2 text-sm">
              <SessionStatusPill status={session.status} />
              <p className="text-buddy-muted">Progress: {session.progress_percent}%</p>
              <p className="text-buddy-muted">Current scene: {session.current_scene}</p>
            </div>
          ) : (
            <p className="text-sm text-buddy-muted">Not started.</p>
          )}
        </Card>

        <Card>
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-buddy-muted">
            Reporting line
          </p>
          <div className="space-y-2">
            {manager && <PersonCard person={manager} role="Manager" />}
            {supervisor && <PersonCard person={supervisor} role="Supervisor" />}
            {!manager && !supervisor && <p className="text-sm text-buddy-muted">Not set.</p>}
          </div>
        </Card>

        <Card>
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-buddy-muted">
            Missions
          </p>
          <p className="text-2xl font-semibold text-buddy-primary">
            {completed}/{mission_assignments.length}
          </p>
          <p className="text-xs text-buddy-muted">completed</p>
        </Card>
      </div>

      <EmployeeDevelopmentSnapshot employeeId={employee.id} />

      <ManagerPerformanceSection employeeId={employee.id} />

      <Card>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-buddy-muted">
          Mission assignments
        </p>
        <ul className="space-y-2">
          {mission_assignments.map((a) => (
            <li
              key={a.id}
              className="flex items-center justify-between rounded-lg border border-buddy-border px-4 py-2 text-sm"
            >
              <span>{a.mission.title}</span>
              <Badge tone={a.status === "completed" ? "success" : "neutral"}>
                {a.status.replace("_", " ")}
              </Badge>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

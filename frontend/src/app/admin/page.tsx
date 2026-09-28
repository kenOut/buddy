"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { EmployeeStatusPill, SessionStatusPill } from "@/components/admin/StatusPill";
import { StatCard } from "@/components/admin/StatCard";
import { Card } from "@/components/ui/Card";
import { api } from "@/lib/api";
import type { AdminOverview } from "@/lib/types";

export default function AdminOverviewPage() {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<AdminOverview>("/admin/overview")
      .then(setOverview)
      .catch(() => setError("Could not reach the Buddy backend on :8000."));
  }, []);

  if (error) return <p className="text-sm text-red-500">{error}</p>;
  if (!overview) return <p className="text-sm text-buddy-muted">Loading overview…</p>;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Overview</h1>
        <p className="mt-1 text-sm text-buddy-muted">
          A snapshot of onboarding progress across the organization.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Employees" value={overview.total_employees} />
        <StatCard label="In progress" value={overview.onboarding_in_progress} />
        <StatCard label="Completed" value={overview.onboarding_completed} />
        <StatCard label="Departments" value={overview.total_departments} />
      </div>

      <Card className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="border-b border-buddy-border text-xs uppercase tracking-wide text-buddy-muted">
              <tr>
                <th className="px-6 py-3">Employee</th>
                <th className="px-6 py-3">Department</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3">Onboarding</th>
                <th className="px-6 py-3">Missions</th>
              </tr>
            </thead>
            <tbody>
              {overview.rows.map((row) => (
                <tr key={row.employee.id} className="border-b border-buddy-border last:border-0">
                  <td className="px-6 py-3">
                    <Link
                      href={`/admin/employees/${row.employee.id}`}
                      className="font-medium text-foreground hover:text-buddy-primary"
                    >
                      {row.employee.full_name}
                    </Link>
                    <p className="text-xs text-buddy-muted">{row.employee.job_title}</p>
                  </td>
                  <td className="px-6 py-3 text-buddy-muted">{row.department?.name ?? "—"}</td>
                  <td className="px-6 py-3">
                    <EmployeeStatusPill status={row.employee.status} />
                  </td>
                  <td className="px-6 py-3">
                    {row.session ? <SessionStatusPill status={row.session.status} /> : "—"}
                  </td>
                  <td className="px-6 py-3 text-buddy-muted">
                    {row.missions_completed}/{row.missions_total}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

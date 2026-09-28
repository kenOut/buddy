"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { WorkspaceIntegrationSection } from "@/components/admin/WorkspaceIntegrationSection";
import { Card } from "@/components/ui/Card";
import { api } from "@/lib/api";
import type { Department, Employee } from "@/lib/types";

export default function DepartmentDetailPage() {
  const params = useParams<{ id: string }>();
  const departmentId = params.id;

  const [department, setDepartment] = useState<Department | null>(null);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Department>(`/departments/${departmentId}`)
      .then(setDepartment)
      .catch(() => setError("Department not found."));
    api.get<Employee[]>(`/employees?department_id=${departmentId}`).then(setEmployees);
  }, [departmentId]);

  if (error) return <p className="text-sm text-buddy-coral">{error}</p>;
  if (!department) return <p className="text-sm text-buddy-muted">Loading…</p>;

  return (
    <div className="space-y-6">
      <Link href="/admin/departments" className="text-sm text-buddy-muted hover:text-foreground">
        ← Back to departments
      </Link>

      <div>
        <h1 className="text-2xl font-semibold">{department.name}</h1>
        {department.description && (
          <p className="mt-1 text-sm text-buddy-muted">{department.description}</p>
        )}
        <p className="mt-1 text-xs uppercase tracking-wide text-buddy-muted">
          {employees.length} {employees.length === 1 ? "employee" : "employees"}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <WorkspaceIntegrationSection departmentId={departmentId} />
        <Card>
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-buddy-muted">Team</p>
          <ul className="space-y-2 text-sm">
            {employees.slice(0, 8).map((employee) => (
              <li key={employee.id} className="flex items-center justify-between">
                <Link
                  href={`/admin/employees/${employee.id}`}
                  className="text-foreground hover:text-buddy-primary"
                >
                  {employee.full_name}
                </Link>
                <span className="text-xs text-buddy-muted">{employee.job_title ?? "—"}</span>
              </li>
            ))}
            {employees.length === 0 && <p className="text-buddy-muted">No employees yet.</p>}
          </ul>
        </Card>
      </div>
    </div>
  );
}

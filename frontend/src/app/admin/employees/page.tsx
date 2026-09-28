"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { EmployeeStatusPill } from "@/components/admin/StatusPill";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { api } from "@/lib/api";
import type { Department, Employee } from "@/lib/types";

export default function EmployeesPage() {
  const [employees, setEmployees] = useState<Employee[] | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [showInactive, setShowInactive] = useState(false);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<Employee[]>("/employees").then(setEmployees);
    api.get<Department[]>("/departments").then(setDepartments);
  }, []);

  async function handleDepartmentChange(employee: Employee, departmentId: string) {
    setError(null);
    setPendingId(employee.id);
    const nextDepartmentId = departmentId === "" ? null : departmentId;
    try {
      const updated = await api.patch<Employee>(`/employees/${employee.id}/department`, {
        department_id: nextDepartmentId,
      });
      setEmployees((prev) => prev?.map((e) => (e.id === employee.id ? updated : e)) ?? prev);
    } catch {
      setError(`Couldn't update ${employee.full_name}'s department. Try again.`);
    } finally {
      setPendingId(null);
    }
  }

  async function handleMarkInactive(employee: Employee) {
    if (!window.confirm(`Mark ${employee.full_name} as inactive? They'll drop off the active roster.`)) {
      return;
    }
    setError(null);
    setPendingId(employee.id);
    try {
      const updated = await api.patch<Employee>(`/employees/${employee.id}/status`, {
        status: "inactive",
      });
      setEmployees((prev) => prev?.map((e) => (e.id === employee.id ? updated : e)) ?? prev);
    } catch {
      setError(`Couldn't mark ${employee.full_name} inactive. Try again.`);
    } finally {
      setPendingId(null);
    }
  }

  async function handleReactivate(employee: Employee) {
    setError(null);
    setPendingId(employee.id);
    try {
      const updated = await api.patch<Employee>(`/employees/${employee.id}/status`, {
        status: "active",
      });
      setEmployees((prev) => prev?.map((e) => (e.id === employee.id ? updated : e)) ?? prev);
    } catch {
      setError(`Couldn't reactivate ${employee.full_name}. Try again.`);
    } finally {
      setPendingId(null);
    }
  }

  const visibleEmployees = employees?.filter((e) =>
    showInactive ? e.status === "inactive" : e.status !== "inactive"
  );
  const inactiveCount = employees?.filter((e) => e.status === "inactive").length ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Employees</h1>
          <p className="mt-1 text-sm text-buddy-muted">Everyone in the organization.</p>
        </div>

        <div className="flex gap-1 rounded-full border border-buddy-border bg-buddy-surface p-1 text-sm">
          <button
            onClick={() => setShowInactive(false)}
            className={`rounded-full px-3 py-1.5 font-medium transition-colors ${
              !showInactive ? "bg-buddy-primary text-white" : "text-buddy-muted hover:text-foreground"
            }`}
          >
            Active
          </button>
          <button
            onClick={() => setShowInactive(true)}
            className={`rounded-full px-3 py-1.5 font-medium transition-colors ${
              showInactive ? "bg-buddy-primary text-white" : "text-buddy-muted hover:text-foreground"
            }`}
          >
            Inactive{inactiveCount > 0 ? ` (${inactiveCount})` : ""}
          </button>
        </div>
      </div>

      {error && (
        <p className="rounded-lg bg-buddy-coral/10 px-4 py-2 text-sm text-red-600">{error}</p>
      )}

      <Card className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="border-b border-buddy-border text-xs uppercase tracking-wide text-buddy-muted">
              <tr>
                <th className="px-6 py-3">Name</th>
                <th className="px-6 py-3">Job title</th>
                <th className="px-6 py-3">Department</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {visibleEmployees?.map((employee) => (
                <tr key={employee.id} className="border-b border-buddy-border last:border-0">
                  <td className="px-6 py-3">
                    <Link
                      href={`/admin/employees/${employee.id}`}
                      className="font-medium text-foreground hover:text-buddy-primary"
                    >
                      {employee.full_name}
                    </Link>
                  </td>
                  <td className="px-6 py-3 text-buddy-muted">{employee.job_title ?? "—"}</td>
                  <td className="px-6 py-3">
                    <select
                      value={employee.department_id ?? ""}
                      disabled={pendingId === employee.id}
                      onChange={(e) => handleDepartmentChange(employee, e.target.value)}
                      className="rounded-lg border border-buddy-border bg-buddy-surface px-2 py-1.5 text-sm text-foreground disabled:opacity-60"
                    >
                      <option value="">No department</option>
                      {departments.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-6 py-3">
                    <EmployeeStatusPill status={employee.status} />
                  </td>
                  <td className="px-6 py-3">
                    {employee.status === "inactive" ? (
                      <Button
                        variant="secondary"
                        disabled={pendingId === employee.id}
                        onClick={() => handleReactivate(employee)}
                        className="px-4 py-1.5 text-xs"
                      >
                        Reactivate
                      </Button>
                    ) : (
                      <Button
                        variant="secondary"
                        disabled={pendingId === employee.id}
                        onClick={() => handleMarkInactive(employee)}
                        className="px-4 py-1.5 text-xs text-red-600 hover:border-buddy-coral"
                      >
                        Mark inactive
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
              {visibleEmployees && visibleEmployees.length === 0 && (
                <tr>
                  <td className="px-6 py-6 text-buddy-muted" colSpan={5}>
                    {showInactive ? "No inactive employees." : "No employees yet."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { EmployeeStatusPill } from "@/components/admin/StatusPill";
import { Avatar } from "@/components/ui/Avatar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import type { Department, Employee } from "@/lib/types";

type SortKey = "name" | "title" | "department";
const PAGE_SIZE = 20;

const controlClass =
  "rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm text-foreground placeholder:text-buddy-muted focus:border-buddy-primary focus:outline-none focus:ring-2 focus:ring-buddy-primary/30 disabled:opacity-60";

export default function EmployeesPage() {
  const [employees, setEmployees] = useState<Employee[] | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<Employee | null>(null);

  const [showInactive, setShowInactive] = useState(false);
  const [query, setQuery] = useState("");
  const [deptFilter, setDeptFilter] = useState<string>("all"); // "all" | "none" | department id
  const [sort, setSort] = useState<SortKey>("name");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const [emps, deps] = await Promise.all([
        api.get<Employee[]>("/employees"),
        api.get<Department[]>("/departments"),
      ]);
      setEmployees(emps);
      setDepartments(deps);
    } catch {
      setLoadError("Couldn't load employees. Check your connection and try again.");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.get<Employee[]>("/employees"),
      api.get<Department[]>("/departments"),
    ])
      .then(([emps, deps]) => {
        if (cancelled) return;
        setEmployees(emps);
        setDepartments(deps);
      })
      .catch(() => {
        if (!cancelled) setLoadError("Couldn't load employees. Check your connection and try again.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filterKey = `${query}|${deptFilter}|${sort}|${showInactive}`;
  const [prevFilterKey, setPrevFilterKey] = useState(filterKey);
  if (filterKey !== prevFilterKey) {
    setPrevFilterKey(filterKey);
    setVisibleCount(PAGE_SIZE);
  }

  async function updateEmployee(employee: Employee, request: () => Promise<Employee>, failure: string) {
    setError(null);
    setPendingId(employee.id);
    try {
      const updated = await request();
      setEmployees((prev) => prev?.map((e) => (e.id === employee.id ? updated : e)) ?? prev);
    } catch {
      setError(failure);
    } finally {
      setPendingId(null);
    }
  }

  function handleDepartmentChange(employee: Employee, departmentId: string) {
    return updateEmployee(
      employee,
      () =>
        api.patch<Employee>(`/employees/${employee.id}/department`, {
          department_id: departmentId === "" ? null : departmentId,
        }),
      `Couldn't update ${employee.full_name}'s department. Try again.`,
    );
  }

  function handleStatusChange(employee: Employee, status: "active" | "inactive") {
    return updateEmployee(
      employee,
      () => api.patch<Employee>(`/employees/${employee.id}/status`, { status }),
      status === "inactive"
        ? `Couldn't mark ${employee.full_name} inactive. Try again.`
        : `Couldn't reactivate ${employee.full_name}. Try again.`,
    );
  }

  const deptName = useMemo(() => new Map(departments.map((d) => [d.id, d.name])), [departments]);

  const inactiveCount = useMemo(() => employees?.filter((e) => e.status === "inactive").length ?? 0, [employees]);
  const activeCount = (employees?.length ?? 0) - inactiveCount;

  const visibleEmployees = useMemo(() => {
    if (!employees) return [];
    const q = query.trim().toLowerCase();
    return employees
      .filter((e) => (showInactive ? e.status === "inactive" : e.status !== "inactive"))
      .filter((e) =>
        deptFilter === "all" ? true : deptFilter === "none" ? !e.department_id : e.department_id === deptFilter,
      )
      .filter((e) => {
        if (!q) return true;
        const dept = e.department_id ? deptName.get(e.department_id) ?? "" : "";
        return `${e.full_name} ${e.job_title ?? ""} ${dept}`.toLowerCase().includes(q);
      })
      .sort((a, b) => {
        if (sort === "title") return (a.job_title ?? "").localeCompare(b.job_title ?? "");
        if (sort === "department") {
          const da = a.department_id ? deptName.get(a.department_id) ?? "" : "";
          const db = b.department_id ? deptName.get(b.department_id) ?? "" : "";
          return da.localeCompare(db);
        }
        return a.full_name.localeCompare(b.full_name);
      });
  }, [employees, showInactive, deptFilter, query, sort, deptName]);

  const hasFilters = query.trim() !== "" || deptFilter !== "all";
  const isLoading = employees === null && !loadError;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Employees</h1>
          <p className="mt-1 text-sm text-buddy-muted">
            {employees ? `${activeCount} active · ${inactiveCount} inactive` : "Everyone in the organization."}
          </p>
        </div>

        <div role="tablist" aria-label="Employee status" className="flex gap-1 rounded-full border border-buddy-border bg-buddy-surface p-1 text-sm">
          {([
            [false, `Active${employees ? ` (${activeCount})` : ""}`],
            [true, `Inactive${inactiveCount > 0 ? ` (${inactiveCount})` : ""}`],
          ] as const).map(([value, label]) => (
            <button
              key={String(value)}
              role="tab"
              aria-selected={showInactive === value}
              onClick={() => setShowInactive(value)}
              className={`rounded-full px-3 py-1.5 font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-buddy-primary/60 ${
                showInactive === value ? "bg-buddy-primary text-white" : "text-buddy-muted hover:text-foreground"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2 lg:flex-row">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search name, job title, department…"
          aria-label="Search employees"
          className={`${controlClass} w-full lg:max-w-sm`}
        />
        <select value={deptFilter} onChange={(e) => setDeptFilter(e.target.value)} aria-label="Filter by department" className={controlClass}>
          <option value="all">All departments</option>
          <option value="none">No department</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)} aria-label="Sort employees" className={controlClass}>
          <option value="name">Sort: Name</option>
          <option value="title">Sort: Job title</option>
          <option value="department">Sort: Department</option>
        </select>
      </div>

      {error && (
        <div role="alert" className="flex items-center justify-between gap-4 rounded-lg border border-buddy-coral/30 bg-buddy-coral/10 px-4 py-2 text-sm">
          <span className="text-buddy-coral">{error}</span>
          <button onClick={() => setError(null)} className="text-xs font-medium text-buddy-muted hover:text-foreground">
            Dismiss
          </button>
        </div>
      )}

      {loadError ? (
        <div role="alert" className="flex items-center justify-between gap-4 rounded-xl border border-buddy-coral/30 bg-buddy-coral/10 px-4 py-3 text-sm">
          <span className="text-buddy-coral">{loadError}</span>
          <Button size="sm" onClick={() => void load()}>Retry</Button>
        </div>
      ) : employees !== null && visibleEmployees.length === 0 ? (
        <EmptyState
          title={hasFilters ? "No employees match your filters" : showInactive ? "No inactive employees" : "No employees yet"}
          description={
            hasFilters
              ? "Try clearing the search or choosing a different department."
              : showInactive
                ? "Employees you mark inactive will appear here."
                : "Employees will appear here once they're added."
          }
          action={
            hasFilters ? (
              <Button variant="secondary" onClick={() => { setQuery(""); setDeptFilter("all"); }}>
                Clear filters
              </Button>
            ) : undefined
          }
        />
      ) : (
        <Card className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="border-b border-buddy-border text-xs uppercase tracking-wide text-buddy-muted">
                <tr>
                  <th scope="col" className="px-6 py-3 font-semibold">Name</th>
                  <th scope="col" className="px-6 py-3 font-semibold">Job title</th>
                  <th scope="col" className="px-6 py-3 font-semibold">Department</th>
                  <th scope="col" className="px-6 py-3 font-semibold">Status</th>
                  <th scope="col" className="px-6 py-3 font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody>
                {isLoading &&
                  Array.from({ length: 6 }).map((_, i) => (
                    <tr key={i} className="border-b border-buddy-border last:border-0">
                      <td className="px-6 py-4" colSpan={5}><Skeleton className="h-8 w-full" /></td>
                    </tr>
                  ))}

                {visibleEmployees.slice(0, visibleCount).map((employee) => {
                  const pending = pendingId === employee.id;
                  return (
                    <tr key={employee.id} className="border-b border-buddy-border transition-colors last:border-0 hover:bg-buddy-border/20">
                      <td className="px-6 py-3">
                        <Link
                          href={`/admin/employees/${employee.id}`}
                          className="group -m-1 flex items-center gap-3 rounded-lg p-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-buddy-primary/60"
                        >
                          <Avatar name={employee.full_name} size="sm" />
                          <span className="font-medium text-foreground group-hover:text-buddy-primary">{employee.full_name}</span>
                        </Link>
                      </td>
                      <td className="px-6 py-3 text-buddy-muted">{employee.job_title ?? "—"}</td>
                      <td className="px-6 py-3">
                        <div className="flex items-center gap-2">
                          <select
                            value={employee.department_id ?? ""}
                            disabled={pending}
                            onChange={(e) => void handleDepartmentChange(employee, e.target.value)}
                            aria-label={`Department for ${employee.full_name}`}
                            className={`${controlClass} max-w-[200px] py-1.5`}
                          >
                            <option value="">No department</option>
                            {departments.map((d) => (
                              <option key={d.id} value={d.id}>{d.name}</option>
                            ))}
                          </select>
                          {pending && <span className="text-xs text-buddy-muted" aria-live="polite">Saving…</span>}
                        </div>
                      </td>
                      <td className="px-6 py-3"><EmployeeStatusPill status={employee.status} /></td>
                      <td className="px-6 py-3">
                        {employee.status === "inactive" ? (
                          <Button variant="secondary" size="sm" disabled={pending} onClick={() => void handleStatusChange(employee, "active")}>
                            Reactivate
                          </Button>
                        ) : (
                          <Button variant="danger" size="sm" disabled={pending} onClick={() => setConfirming(employee)}>
                            Mark inactive
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {!isLoading && (
            <div className="flex items-center justify-between border-t border-buddy-border px-6 py-3 text-xs text-buddy-muted">
              <span aria-live="polite">
                Showing {Math.min(visibleCount, visibleEmployees.length)} of {visibleEmployees.length}
              </span>
              {visibleCount < visibleEmployees.length && (
                <button onClick={() => setVisibleCount((n) => n + PAGE_SIZE)} className="font-medium text-buddy-primary hover:underline">
                  Show more
                </button>
              )}
            </div>
          )}
        </Card>
      )}

      <ConfirmDialog
        open={confirming !== null}
        title={`Mark ${confirming?.full_name ?? "employee"} as inactive?`}
        description="They'll drop off the active roster. You can reactivate them any time from the Inactive tab."
        confirmLabel="Mark inactive"
        tone="danger"
        busy={confirming !== null && pendingId === confirming.id}
        onCancel={() => setConfirming(null)}
        onConfirm={async () => {
          if (!confirming) return;
          await handleStatusChange(confirming, "inactive");
          setConfirming(null);
        }}
      />
    </div>
  );
}

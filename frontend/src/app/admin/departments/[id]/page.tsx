"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { NewDepartmentModal } from "@/components/admin/NewDepartmentModal";
import { WorkspaceIntegrationSection } from "@/components/admin/WorkspaceIntegrationSection";
import { Avatar } from "@/components/ui/Avatar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { api, ApiError } from "@/lib/api";
import type { Department, Employee } from "@/lib/types";

export default function DepartmentDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const departmentId = params.id;

  const [department, setDepartment] = useState<Department | null>(null);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [teamQuery, setTeamQuery] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const [prevDepartmentId, setPrevDepartmentId] = useState(departmentId);
  if (departmentId !== prevDepartmentId) {
    setPrevDepartmentId(departmentId);
    setDepartment(null);
    setError(null);
    setShowAll(false);
  }

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      api.get<Department>(`/departments/${departmentId}`),
      api.get<Employee[]>(`/employees?department_id=${departmentId}`),
    ])
      .then(([dep, emps]) => {
        if (cancelled) return;
        setDepartment(dep);
        setEmployees(emps);
      })
      .catch(() => {
        if (!cancelled) setError("Department not found or couldn't be loaded.");
      });

    return () => {
      cancelled = true;
    };
  }, [departmentId]);

  if (error) {
    return (
      <div className="space-y-4">
        <Link href="/admin/departments" className="text-sm text-buddy-muted hover:text-foreground">← Back to departments</Link>
        <EmptyState title="We couldn't open this department" description={error} />
      </div>
    );
  }

  if (!department) {
    return (
      <div className="space-y-6" aria-busy="true">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      </div>
    );
  }

  const filtered = employees.filter((e) =>
    e.full_name.toLowerCase().includes(teamQuery.trim().toLowerCase()),
  );
  const shown = showAll || teamQuery ? filtered : filtered.slice(0, 8);

  async function handleDelete() {
    if (!department) return;
    setDeleting(true);
    try {
      await api.delete(`/departments/${department.id}`);
      router.push("/admin/departments");
    } catch (err) {
      setDeleteError(
        err instanceof ApiError && err.status === 409
          ? "This department still has employees assigned to it. Move them to another department before deleting it."
          : "Couldn't delete the department. Try again.",
      );
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-6">
      <nav aria-label="Breadcrumb" className="text-sm text-buddy-muted">
        <Link href="/admin/departments" className="hover:text-foreground">Departments</Link>
        <span className="mx-2" aria-hidden>/</span>
        <span className="text-foreground">{department.name}</span>
      </nav>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-4">
          <Avatar name={department.name} />
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight">{department.name}</h1>
            {department.description && (
              <p className="mt-1 max-w-2xl text-sm text-buddy-muted">{department.description}</p>
            )}
            <span className="mt-2 inline-flex rounded-full bg-buddy-primary/10 px-2.5 py-0.5 text-xs font-medium text-buddy-primary">
              {employees.length} {employees.length === 1 ? "employee" : "employees"}
            </span>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" onClick={() => setShowEdit(true)}>
            Edit
          </Button>
          <Button
            variant="danger"
            size="sm"
            onClick={() => {
              setDeleteError(null);
              setConfirmingDelete(true);
            }}
          >
            Delete
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <WorkspaceIntegrationSection departmentId={departmentId} />
        <Card>
          <div className="mb-3 flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">Team</p>
            <span className="text-xs text-buddy-muted">{employees.length}</span>
          </div>

          {employees.length > 8 && (
            <input
              type="search"
              value={teamQuery}
              onChange={(e) => setTeamQuery(e.target.value)}
              placeholder="Find a teammate…"
              aria-label="Find a teammate"
              className="mb-3 w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm text-foreground placeholder:text-buddy-muted focus:border-buddy-primary focus:outline-none focus:ring-2 focus:ring-buddy-primary/30"
            />
          )}

          {employees.length === 0 ? (
            <EmptyState title="No employees yet" description="People assigned to this department will appear here." />
          ) : (
            <ul className="divide-y divide-buddy-border text-sm">
              {shown.map((employee) => (
                <li key={employee.id}>
                  <Link
                    href={`/admin/employees/${employee.id}`}
                    className="group flex items-center gap-3 rounded-lg px-2 py-2.5 transition-colors hover:bg-buddy-border/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-buddy-primary/60"
                  >
                    <Avatar name={employee.full_name} size="sm" />
                    <span className="flex-1 truncate text-foreground group-hover:text-buddy-primary">{employee.full_name}</span>
                    <span className="truncate text-xs text-buddy-muted">{employee.job_title ?? "—"}</span>
                  </Link>
                </li>
              ))}
              {shown.length === 0 && <li className="py-3 text-buddy-muted">No matches.</li>}
            </ul>
          )}

          {!teamQuery && !showAll && employees.length > 8 && (
            <button onClick={() => setShowAll(true)} className="mt-3 text-sm text-buddy-primary hover:underline">
              Show all {employees.length} →
            </button>
          )}
        </Card>
      </div>

      {showEdit && (
        <NewDepartmentModal
          organizationId={department.organization_id}
          department={department}
          onClose={() => setShowEdit(false)}
          onCreated={(updated) => setDepartment(updated)}
        />
      )}

      <ConfirmDialog
        open={confirmingDelete}
        title={`Delete ${department.name}?`}
        description={
          deleteError ??
          "This can't be undone. Its roles, teams, projects, and workspace connection go with it; any missions and quests it owns are kept but unassigned from it."
        }
        confirmLabel="Delete"
        tone="danger"
        busy={deleting}
        onCancel={() => {
          setConfirmingDelete(false);
          setDeleteError(null);
        }}
        onConfirm={handleDelete}
      />
    </div>
  );
}

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { NewDepartmentModal } from "@/components/admin/NewDepartmentModal";
import { Avatar } from "@/components/ui/Avatar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import type { Department, Employee, Organization } from "@/lib/types";

export default function DepartmentsPage() {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [organizationId, setOrganizationId] = useState<string | null>(null);
  const [showNewDepartment, setShowNewDepartment] = useState(false);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"name" | "headcount">("name");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [deps, emps, orgs] = await Promise.all([
        api.get<Department[]>("/departments"),
        api.get<Employee[]>("/employees"),
        api.get<Organization[]>("/organizations"),
      ]);
      setDepartments(deps);
      setEmployees(emps);
      setOrganizationId(orgs[0]?.id ?? null);
    } catch {
      setError("We couldn't load departments. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.get<Department[]>("/departments"),
      api.get<Employee[]>("/employees"),
      api.get<Organization[]>("/organizations"),
    ])
      .then(([deps, emps, orgs]) => {
        if (cancelled) return;
        setDepartments(deps);
        setEmployees(emps);
        setOrganizationId(orgs[0]?.id ?? null);
      })
      .catch(() => {
        if (!cancelled) setError("We couldn't load departments. Check your connection and try again.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const headcountById = useMemo(() => {
    const map = new Map<string, number>();
    for (const e of employees) {
      if (e.department_id) map.set(e.department_id, (map.get(e.department_id) ?? 0) + 1);
    }
    return map;
  }, [employees]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return departments
      .filter((d) => !q || d.name.toLowerCase().includes(q) || d.description?.toLowerCase().includes(q))
      .sort((a, b) =>
        sort === "headcount"
          ? (headcountById.get(b.id) ?? 0) - (headcountById.get(a.id) ?? 0)
          : a.name.localeCompare(b.name),
      );
  }, [departments, query, sort, headcountById]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Departments</h1>
          <p className="mt-1 text-sm text-buddy-muted">
            {loading ? "Loading org structure…" : `${departments.length} departments · ${employees.length} employees`}
          </p>
        </div>
        <Button title={!organizationId ? "Loading organization…" : undefined} disabled={!organizationId} onClick={() => setShowNewDepartment(true)}>
          New department
        </Button>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search departments…"
          aria-label="Search departments"
          className="w-full flex-1 rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm text-foreground placeholder:text-buddy-muted focus:border-buddy-primary focus:outline-none focus:ring-2 focus:ring-buddy-primary/30"
        />
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as "name" | "headcount")}
          aria-label="Sort departments"
          className="rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm text-foreground focus:border-buddy-primary focus:outline-none focus:ring-2 focus:ring-buddy-primary/30"
        >
          <option value="name">Sort: Name</option>
          <option value="headcount">Sort: Headcount</option>
        </select>
      </div>

      {showNewDepartment && organizationId && (
        <NewDepartmentModal
          organizationId={organizationId}
          onClose={() => setShowNewDepartment(false)}
          onCreated={(department) => setDepartments((prev) => [...prev, department])}
        />
      )}

      {error ? (
        <div role="alert" className="flex items-center justify-between gap-4 rounded-xl border border-buddy-coral/30 bg-buddy-coral/10 px-4 py-3 text-sm">
          <span className="text-buddy-coral">{error}</span>
          <Button onClick={() => void load()}>Retry</Button>
        </div>
      ) : loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i}>
              <Skeleton className="h-10 w-10" />
              <Skeleton className="mt-4 h-4 w-2/3" />
              <Skeleton className="mt-2 h-3 w-full" />
              <Skeleton className="mt-4 h-3 w-1/4" />
            </Card>
          ))}
        </div>
      ) : visible.length === 0 ? (
        <EmptyState
          title={query ? "No matching departments" : "No departments yet"}
          description={query ? "Try a different search term." : "Create your first department to start organizing teams and onboarding paths."}
          action={!query && organizationId ? <Button onClick={() => setShowNewDepartment(true)}>New department</Button> : undefined}
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {visible.map((department) => {
            const headcount = headcountById.get(department.id) ?? 0;
            return (
              <Link
                key={department.id}
                href={`/admin/departments/${department.id}`}
                className="group block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-buddy-primary/60"
              >
                <Card className="h-full transition-all duration-200 group-hover:-translate-y-0.5 group-hover:border-buddy-primary/50 group-hover:shadow-lg group-hover:shadow-buddy-primary/5">
                  <div className="flex items-start justify-between gap-3">
                    <Avatar name={department.name} />
                    <span aria-hidden className="text-buddy-muted transition-transform group-hover:translate-x-0.5 group-hover:text-buddy-primary">→</span>
                  </div>
                  <p className="mt-3 font-medium text-foreground">{department.name}</p>
                  <p className="mt-1 line-clamp-2 min-h-[2.5rem] text-sm text-buddy-muted">
                    {department.description || "No description yet."}
                  </p>
                  <p className="mt-3 text-xs uppercase tracking-wide text-buddy-muted">
                    {headcount} {headcount === 1 ? "employee" : "employees"}
                  </p>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

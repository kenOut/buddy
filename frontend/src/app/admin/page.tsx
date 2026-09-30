"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { EmployeeStatusPill, SessionStatusPill } from "@/components/admin/StatusPill";
import { StatCard } from "@/components/admin/StatCard";
import { Avatar } from "@/components/ui/Avatar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import type { AdminOverview } from "@/lib/types";

type ProgressFilter = "all" | "not_started" | "in_progress" | "complete";
type SortKey = "name" | "progress_low" | "progress_high";
type OverviewRow = AdminOverview["rows"][number];

const PAGE_SIZE = 15;

const pct = (done: number, total: number) => (total > 0 ? Math.round((done / total) * 100) : 0);

function MissionProgress({ done, total }: { done: number; total: number }) {
  const value = pct(done, total);
  return (
    <div className="flex items-center gap-3">
      <div
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${done} of ${total} missions completed`}
        className="h-1.5 w-24 overflow-hidden rounded-full bg-buddy-border"
      >
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            value === 100 ? "bg-buddy-aurora" : "bg-buddy-primary"
          }`}
          style={{ width: `${value}%` }}
        />
      </div>
      <span className="text-xs tabular-nums text-buddy-muted">
        {done}/{total}
      </span>
    </div>
  );
}

function exportCsv(rows: OverviewRow[]) {
  const esc = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`;
  const lines = [["Name", "Role", "Department", "Missions done", "Missions total"].map(esc).join(",")];
  rows.forEach((r) =>
    lines.push(
      [
        r.employee.full_name,
        r.employee.job_title ?? "",
        r.department?.name ?? "",
        r.missions_completed,
        r.missions_total,
      ]
        .map(esc)
        .join(","),
    ),
  );
  const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: "onboarding-progress.csv" });
  a.click();
  URL.revokeObjectURL(url);
}

export default function AdminOverviewPage() {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<ProgressFilter>("all");
  const [sort, setSort] = useState<SortKey>("name");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setError(null);
    try {
      const data = await api.get<AdminOverview>("/admin/overview");
      setOverview(data);
      setLastUpdated(new Date());
      setError(null);
    } catch {
      if (!silent) setError("Could not reach the Buddy backend on :8000.");
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .get<AdminOverview>("/admin/overview")
      .then((data) => {
        if (cancelled) return;
        setOverview(data);
        setLastUpdated(new Date());
        setError(null);
      })
      .catch(() => {
        if (!cancelled) setError("Could not reach the Buddy backend on :8000.");
      });
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") void load(true);
    }, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [load]);

  const filterKey = `${query}|${filter}|${sort}`;
  const [prevFilterKey, setPrevFilterKey] = useState(filterKey);
  if (filterKey !== prevFilterKey) {
    setPrevFilterKey(filterKey);
    setVisibleCount(PAGE_SIZE);
  }

  const rows = overview?.rows;

  const filteredRows = useMemo(() => {
    if (!rows) return [];
    const q = query.trim().toLowerCase();
    return rows
      .filter((r) => {
        if (q) {
          const haystack = `${r.employee.full_name} ${r.employee.job_title ?? ""} ${
            r.department?.name ?? ""
          }`.toLowerCase();
          if (!haystack.includes(q)) return false;
        }
        const done = r.missions_completed;
        const total = r.missions_total;
        if (filter === "not_started") return done === 0;
        if (filter === "in_progress") return done > 0 && done < total;
        if (filter === "complete") return total > 0 && done >= total;
        return true;
      })
      .sort((a, b) => {
        if (sort === "name") return a.employee.full_name.localeCompare(b.employee.full_name);
        const diff = pct(a.missions_completed, a.missions_total) - pct(b.missions_completed, b.missions_total);
        return sort === "progress_low" ? diff : -diff;
      });
  }, [rows, query, filter, sort]);

  const counts = useMemo(() => {
    const c = { all: rows?.length ?? 0, not_started: 0, in_progress: 0, complete: 0 };
    rows?.forEach((r) => {
      if (r.missions_completed === 0) c.not_started++;
      else if (r.missions_total > 0 && r.missions_completed >= r.missions_total) c.complete++;
      else c.in_progress++;
    });
    return c;
  }, [rows]);

  if (error && !overview) {
    return (
      <div
        role="alert"
        className="flex items-center justify-between gap-4 rounded-xl border border-buddy-coral/30 bg-buddy-coral/10 px-4 py-3 text-sm"
      >
        <span className="text-buddy-coral">{error}</span>
        <Button onClick={() => void load()}>Retry</Button>
      </div>
    );
  }

  if (!overview) {
    return (
      <div className="space-y-8" aria-busy="true">
        <div className="space-y-2">
          <Skeleton className="h-8 w-40" />
          <Skeleton className="h-4 w-72" />
        </div>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-96" />
      </div>
    );
  }

  const completionPct = pct(overview.onboarding_completed, overview.total_employees);
  const inProgressPct = pct(overview.onboarding_in_progress, overview.total_employees);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-semibold tracking-tight">Overview</h1>
          <p className="mt-1 text-sm text-buddy-muted">
            A snapshot of onboarding progress across the organization.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-xs text-buddy-muted" aria-live="polite">
              Updated {lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
          <Button
            variant="secondary"
            onClick={() => exportCsv(filteredRows)}
            disabled={filteredRows.length === 0}
          >
            Export CSV
          </Button>
          <Button variant="secondary" onClick={() => void load(true)} disabled={refreshing}>
            <span className={refreshing ? "animate-spin" : ""} aria-hidden>
              ↻
            </span>
            {refreshing ? "Refreshing…" : "Refresh"}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Employees" value={overview.total_employees} />
        <StatCard label="In progress" value={overview.onboarding_in_progress} />
        <StatCard label="Completed" value={overview.onboarding_completed} />
        <StatCard label="Departments" value={overview.total_departments} />
      </div>

      {overview.total_employees > 0 && (
        <Card className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:gap-6">
          <div className="shrink-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">
              Org completion rate
            </p>
            <p className="font-heading text-2xl font-semibold tabular-nums text-foreground">
              {completionPct}%
            </p>
          </div>
          <div
            role="progressbar"
            aria-valuenow={completionPct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Organization onboarding completion"
            className="flex h-2.5 flex-1 overflow-hidden rounded-full bg-buddy-border"
          >
            <div className="bg-buddy-aurora transition-all duration-700" style={{ width: `${completionPct}%` }} />
            <div className="bg-buddy-primary/60 transition-all duration-700" style={{ width: `${inProgressPct}%` }} />
          </div>
          <div className="flex shrink-0 gap-4 text-xs text-buddy-muted">
            <span className="flex items-center gap-1.5">
              <i className="h-2 w-2 rounded-full bg-buddy-aurora" />
              Completed
            </span>
            <span className="flex items-center gap-1.5">
              <i className="h-2 w-2 rounded-full bg-buddy-primary/60" />
              In progress
            </span>
          </div>
        </Card>
      )}

      <section className="space-y-3" aria-label="Employees onboarding progress">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div role="tablist" aria-label="Filter by progress" className="flex flex-wrap gap-1.5">
            {(
              [
                ["all", "All"],
                ["not_started", "Not started"],
                ["in_progress", "In progress"],
                ["complete", "Complete"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                role="tab"
                aria-selected={filter === value}
                onClick={() => setFilter(value)}
                className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-buddy-primary/60 ${
                  filter === value
                    ? "bg-buddy-primary/10 text-buddy-primary"
                    : "text-buddy-muted hover:bg-buddy-border/40 hover:text-foreground"
                }`}
              >
                {label} <span className="ml-1 tabular-nums opacity-70">{counts[value]}</span>
              </button>
            ))}
          </div>

          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search name, role, department…"
              aria-label="Search employees"
              className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm text-foreground placeholder:text-buddy-muted focus:border-buddy-primary focus:outline-none focus:ring-2 focus:ring-buddy-primary/30 sm:w-64"
            />
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              aria-label="Sort employees"
              className="rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm text-foreground focus:border-buddy-primary focus:outline-none focus:ring-2 focus:ring-buddy-primary/30"
            >
              <option value="name">Sort: Name</option>
              <option value="progress_low">Sort: Furthest behind</option>
              <option value="progress_high">Sort: Most progress</option>
            </select>
          </div>
        </div>

        {filteredRows.length === 0 ? (
          <EmptyState
            title={rows?.length ? "No employees match your filters" : "No employees yet"}
            description={
              rows?.length
                ? "Try clearing the search or choosing a different filter."
                : "Employees will appear here once they're added and begin onboarding."
            }
            action={
              rows?.length ? (
                <Button
                  variant="secondary"
                  onClick={() => {
                    setQuery("");
                    setFilter("all");
                  }}
                >
                  Clear filters
                </Button>
              ) : undefined
            }
          />
        ) : (
          <Card className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="border-b border-buddy-border bg-buddy-surface text-xs uppercase tracking-wide text-buddy-muted">
                  <tr>
                    <th scope="col" className="px-6 py-3 font-semibold">Employee</th>
                    <th scope="col" className="px-6 py-3 font-semibold">Department</th>
                    <th scope="col" className="px-6 py-3 font-semibold">Status</th>
                    <th scope="col" className="px-6 py-3 font-semibold">Onboarding</th>
                    <th scope="col" className="px-6 py-3 font-semibold">Missions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.slice(0, visibleCount).map((row) => (
                    <tr
                      key={row.employee.id}
                      className="border-b border-buddy-border transition-colors last:border-0 hover:bg-buddy-border/20"
                    >
                      <td className="px-6 py-3">
                        <Link
                          href={`/admin/employees/${row.employee.id}`}
                          className="group -m-1 flex items-center gap-3 rounded-lg p-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-buddy-primary/60"
                        >
                          <Avatar name={row.employee.full_name} size="sm" />
                          <span className="min-w-0">
                            <span className="block truncate font-medium text-foreground group-hover:text-buddy-primary">
                              {row.employee.full_name}
                            </span>
                            <span className="block truncate text-xs text-buddy-muted">
                              {row.employee.job_title ?? "—"}
                            </span>
                          </span>
                        </Link>
                      </td>
                      <td className="px-6 py-3 text-buddy-muted">{row.department?.name ?? "—"}</td>
                      <td className="px-6 py-3">
                        <EmployeeStatusPill status={row.employee.status} />
                      </td>
                      <td className="px-6 py-3">
                        {row.session ? (
                          <SessionStatusPill status={row.session.status} />
                        ) : (
                          <span className="text-buddy-muted">—</span>
                        )}
                      </td>
                      <td className="px-6 py-3">
                        <MissionProgress done={row.missions_completed} total={row.missions_total} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between border-t border-buddy-border px-6 py-3 text-xs text-buddy-muted">
              <span aria-live="polite">
                Showing {Math.min(visibleCount, filteredRows.length)} of {filteredRows.length}
              </span>
              {visibleCount < filteredRows.length && (
                <button
                  onClick={() => setVisibleCount((n) => n + PAGE_SIZE)}
                  className="font-medium text-buddy-primary hover:underline"
                >
                  Show more
                </button>
              )}
            </div>
          </Card>
        )}
      </section>
    </div>
  );
}

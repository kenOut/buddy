"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { getEmployeeAnalytics } from "@/lib/analytics";
import type { EmployeeAnalytics } from "@/lib/types";

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return iso;
  }
}

/**
 * Phase 6E Part 12 — added to the existing employee detail page rather
 * than a duplicate profile. Shows only what analytics_service.py
 * already computes: capabilities observed, current development areas,
 * recent Quest activity, and the latest recommendation. Links out to
 * the full Development Journey rather than repeating its timeline here.
 */
export function EmployeeDevelopmentSnapshot({ employeeId }: { employeeId: string }) {
  const [data, setData] = useState<EmployeeAnalytics | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getEmployeeAnalytics(employeeId)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [employeeId]);

  if (error) return null;
  if (!data) {
    return (
      <Card>
        <p className="text-sm text-buddy-muted">Loading development snapshot…</p>
      </Card>
    );
  }

  const observedCount = data.capabilities.filter((c) => c.level !== "NOT_OBSERVED").length;
  const recentCompleted = data.recent_quest_activity.filter((a) => a.status === "COMPLETED").slice(0, 3);

  return (
    <Card>
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">
          Development snapshot
        </p>
        <Link
          href={`/admin/employees/${employeeId}/journey`}
          className="text-xs font-medium text-buddy-primary hover:underline"
        >
          Full development journey →
        </Link>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <p className="text-xl font-semibold text-buddy-primary">{observedCount}/6</p>
          <p className="text-xs text-buddy-muted">capabilities observed</p>
        </div>
        <div>
          <p className="text-xl font-semibold text-buddy-primary">{data.recent_quest_activity.length}</p>
          <p className="text-xs text-buddy-muted">recent Quest activity</p>
        </div>
      </div>

      {data.development_areas.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">
            Current development areas
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {data.development_areas.map((key) => {
              const cap = data.capabilities.find((c) => c.capability_key === key);
              return (
                <Badge key={key} tone="neutral">
                  {cap?.capability_name ?? key}
                </Badge>
              );
            })}
          </div>
        </div>
      )}

      {recentCompleted.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">
            Recently completed Quests
          </p>
          <ul className="mt-1.5 space-y-1 text-sm text-buddy-text-secondary">
            {recentCompleted.map((a) => (
              <li key={a.quest_id}>
                {a.quest_title} — {formatDate(a.completed_at)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.latest_recommendation && (
        <div className="mt-4 border-t border-buddy-border pt-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">
            Latest recommendation
          </p>
          <p className="mt-1 text-sm text-buddy-text-primary">{data.latest_recommendation.quest_title}</p>
          <p className="text-xs text-buddy-muted">{data.latest_recommendation.reason}</p>
        </div>
      )}
    </Card>
  );
}

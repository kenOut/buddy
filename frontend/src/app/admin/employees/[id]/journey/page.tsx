"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { CurrentSnapshotCard } from "@/components/journey/CurrentSnapshotCard";
import { JourneyTimeline } from "@/components/journey/JourneyTimeline";
import { api } from "@/lib/api";
import { getDevelopmentJourney } from "@/lib/journey";
import type { DevelopmentJourneyResponse, OnboardingBundle } from "@/lib/types";

/**
 * Phase 6E Part 12 — a manager-facing, read-only view of an arbitrary
 * employee's development journey.
 *
 * Why this exists instead of linking to /onboarding/journey: that page
 * is hardcoded to the single demo identity via useOnboarding() (see
 * lib/onboarding-context.tsx), which resolves GET /onboarding/bundle/
 * demo — it has no way to target a manager-selected employee_id, and
 * mounting the full onboarding-scene layout/progress-indicator chrome
 * for a manager drill-down doesn't fit this context anyway. The
 * backend GET /employees/{id}/development-journey endpoint (Phase 6D)
 * is already fully general-purpose, and JourneyTimeline/
 * CurrentSnapshotCard both take `items` as plain props with no
 * dependency on onboarding context — so this page reuses those exact
 * components rather than duplicating timeline-rendering logic, without
 * touching any Phase 6D file.
 */
export default function EmployeeJourneyPage() {
  const params = useParams<{ id: string }>();
  const employeeId = params.id;

  const [journey, setJourney] = useState<DevelopmentJourneyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [name, setName] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getDevelopmentJourney(employeeId)
      .then((data) => {
        if (!cancelled) setJourney(data);
      })
      .catch(() => {
        if (!cancelled) setError("Couldn't load this employee's development journey.");
      });
    return () => {
      cancelled = true;
    };
  }, [employeeId, attempt]);

  useEffect(() => {
    let cancelled = false;
    api
      .get<OnboardingBundle>(`/onboarding/bundle/${employeeId}`)
      .then((b) => {
        if (!cancelled) setName(b.employee.full_name);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [employeeId]);

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <nav aria-label="Breadcrumb" className="text-sm text-buddy-muted">
        <Link href="/admin/employees" className="hover:text-foreground">Employees</Link>
        <span className="mx-2" aria-hidden>/</span>
        <Link href={`/admin/employees/${employeeId}`} className="hover:text-foreground">{name ?? "Employee"}</Link>
        <span className="mx-2" aria-hidden>/</span>
        <span className="text-foreground">Journey</span>
      </nav>

      <div>
        <h1 className="font-heading text-2xl font-semibold tracking-tight">
          {name ? `${name}'s development journey` : "Development journey"}
        </h1>
        <p className="mt-1 text-sm text-buddy-muted">A read-only view of what Buddy has observed for this employee.</p>
      </div>

      {error ? (
        <div role="alert" className="flex items-center justify-between gap-4 rounded-xl border border-buddy-coral/30 bg-buddy-coral/10 px-4 py-3 text-sm">
          <span className="text-buddy-coral">{error}</span>
          <Button size="sm" onClick={() => { setJourney(null); setError(null); setAttempt((n) => n + 1); }}>Retry</Button>
        </div>
      ) : !journey ? (
        <div className="space-y-4" aria-busy="true">
          <Skeleton className="h-32" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : journey.items.length === 0 ? (
        <EmptyState
          title="No journey activity yet"
          description="Buddy hasn't recorded any observations for this employee. Entries appear as they complete missions and reflections."
        />
      ) : (
        <>
          <CurrentSnapshotCard items={journey.items} />
          <JourneyTimeline items={journey.items} />
        </>
      )}
    </div>
  );
}

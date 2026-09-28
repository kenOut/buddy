"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { Card } from "@/components/ui/Card";
import { CurrentSnapshotCard } from "@/components/journey/CurrentSnapshotCard";
import { JourneyTimeline } from "@/components/journey/JourneyTimeline";
import { getDevelopmentJourney } from "@/lib/journey";
import type { DevelopmentJourneyResponse } from "@/lib/types";

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
  }, [employeeId]);

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Link href={`/admin/employees/${employeeId}`} className="text-sm text-buddy-muted hover:text-foreground">
        ← Back to employee
      </Link>

      <div>
        <h1 className="text-2xl font-semibold">Development Journey</h1>
        <p className="mt-1 text-sm text-buddy-muted">
          A read-only view of what Buddy has observed for this employee.
        </p>
      </div>

      {error && (
        <Card>
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        </Card>
      )}

      {!journey && !error && <p className="text-sm text-buddy-muted">Loading…</p>}

      {journey && journey.items.length === 0 && (
        <Card>
          <p className="text-sm text-buddy-muted">Your journey starts here.</p>
        </Card>
      )}

      {journey && journey.items.length > 0 && (
        <>
          <CurrentSnapshotCard items={journey.items} />
          <JourneyTimeline items={journey.items} />
        </>
      )}
    </div>
  );
}

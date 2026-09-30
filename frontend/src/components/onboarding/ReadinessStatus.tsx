"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

import { getReadinessSummary } from "@/lib/capabilities";
import { useOnboarding } from "@/lib/onboarding-context";
import type { EmployeeReadinessSummary } from "@/lib/types";

/**
 * Phase 8H-4 — a compact, persistent readiness indicator, mounted once
 * in OnboardingChrome so it's visible across every employee-facing
 * route (scenes, Quest Workspace, Journey), not scene-gated the way
 * ProgressIndicator deliberately is.
 *
 * Purely a consumer of GET /employees/{id}/readiness-summary
 * (readiness_service.get_readiness_summary, Phase 8H-1) — no readiness
 * math, eligibility, or "ready" inference happens here. `summary.ready`
 * is rendered exactly as returned, never recomputed.
 *
 * Deliberately fails closed: a loading or errored fetch renders
 * nothing, and zero required quests-or-missions renders nothing too
 * (there is nothing honest to report yet, and a "0 of 0, not ready"
 * pill would read as an error rather than a legitimate "no required
 * work assigned" state) — this surface must never compete with or
 * destabilize the primary onboarding/Quest/Mission content around it.
 *
 * Readiness is now gated on required Quests AND required Missions
 * (readiness_service.py) — this pill reports the combined total rather
 * than Quests alone, naming whichever kind(s) are actually in play so
 * the copy doesn't lie by omission when only one kind is configured.
 *
 * Refetches on pathname change, not just on mount (small fix, pre-demo
 * freeze): this component is mounted once in OnboardingChrome and never
 * unmounts across onboarding navigation, so `bundle` alone isn't a
 * reliable "the employee did something that could have changed
 * readiness" signal — completing a Quest goes through lib/quests.ts
 * entirely, which never touches the onboarding bundle/context. Quest
 * and Mission completion both always end with a navigation (back to a
 * Quest/Mission list, to the Journey, forward through the next scene),
 * so the route changing is the actual, existing signal that "the
 * employee has returned to an onboarding surface" — not a fixed timer,
 * not polling.
 */
function requiredNoun(summary: EmployeeReadinessSummary): string {
  const hasQuests = summary.required_quest_count > 0;
  const hasMissions = summary.required_mission_count > 0;
  if (hasQuests && !hasMissions) return summary.required_quest_count === 1 ? "quest" : "quests";
  if (hasMissions && !hasQuests) return summary.required_mission_count === 1 ? "mission" : "missions";
  return "items";
}

export function ReadinessStatus() {
  const { bundle } = useOnboarding();
  const pathname = usePathname();
  const [summary, setSummary] = useState<EmployeeReadinessSummary | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!bundle) return;
    let cancelled = false;
    getReadinessSummary(bundle.employee.id)
      .then((result) => {
        if (cancelled) return;
        setSummary(result);
        // A fresh fetch on this navigation succeeded — clear any earlier
        // failure so the pill can recover on its own instead of staying
        // hidden forever after one transient error.
        setFailed(false);
      })
      .catch(() => {
        if (cancelled) return;
        setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [bundle, pathname]);

  const totalRequired = summary ? summary.required_quest_count + summary.required_mission_count : 0;
  const totalCompleted = summary
    ? summary.completed_required_quest_count + summary.completed_required_mission_count
    : 0;

  if (!bundle || failed || !summary || totalRequired === 0) return null;

  const noun = requiredNoun(summary);
  // Stage 2 — an aggregate-only signal (see EmployeeReadinessSummary's
  // own docstring for why this is a count, never a per-item score):
  // a required item can be "complete" above and still be the reason
  // `ready` is false, if it didn't meet its configured minimum score.
  // `summary.ready` itself already reflects that server-side; this line
  // just explains it, rather than leaving "not ready" unexplained when
  // every required item otherwise looks complete.
  const belowThreshold = summary.required_items_below_threshold;

  return (
    <div
      role="status"
      aria-live="polite"
      className={
        summary.ready
          ? "flex w-fit items-center gap-2 rounded-full bg-buddy-primary/10 px-3 py-1.5 text-xs font-medium text-buddy-primary-dark"
          : "flex w-fit items-center gap-2 rounded-full border border-buddy-border bg-buddy-surface px-3 py-1.5 text-xs font-medium text-buddy-muted"
      }
    >
      {summary.ready ? (
        <>
          <span aria-hidden="true">✓</span>
          <span>
            You&rsquo;re ready — {totalCompleted} of {totalRequired} required {noun} complete
          </span>
        </>
      ) : (
        <span>
          {totalCompleted} of {totalRequired} required {noun} complete
          {belowThreshold > 0 &&
            ` — ${belowThreshold} below performance threshold`}
        </span>
      )}
    </div>
  );
}

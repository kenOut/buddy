import { Card } from "@/components/ui/Card";
import type { AnalyticsOverview } from "@/lib/types";

/**
 * Phase 6E Part 5 — a deterministic funnel over QuestAttempt's real
 * lifecycle states, cumulative (each stage = "reached at least this
 * far"), matching analytics_service.py's own `_cumulative_attempt_stage_
 * count` semantics exactly. "Assigned" is a separate, distinct number
 * (resolved from active QuestAssignments, not from QuestAttempt at
 * all) — a Quest being published is not the same as being assigned,
 * and being assigned is not the same as being attempted.
 *
 * Plain CSS bars, no charting library — each bar answers "how many
 * attempts reached this stage," nothing decorative.
 */
export function QuestActivityFunnel({ overview }: { overview: AnalyticsOverview }) {
  const stages = [
    { label: "Assigned", value: overview.employees_reached },
    { label: "Started", value: overview.attempts_total },
    {
      label: "Submitted",
      value: overview.attempts_submitted + overview.attempts_evaluating + overview.attempts_completed,
    },
    { label: "Evaluating", value: overview.attempts_evaluating + overview.attempts_completed },
    { label: "Completed", value: overview.attempts_completed },
  ];
  const max = Math.max(1, ...stages.map((s) => s.value));

  if (overview.published_quests === 0 && overview.employees_reached === 0) {
    return (
      <Card>
        <p className="text-sm text-buddy-muted">No Quest activity yet.</p>
      </Card>
    );
  }

  return (
    <Card className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
        Quest completion funnel
      </p>
      <div className="space-y-2">
        {stages.map((stage) => (
          <div key={stage.label} className="flex items-center gap-3">
            <span className="w-24 shrink-0 text-xs text-buddy-muted">{stage.label}</span>
            <div className="h-5 flex-1 overflow-hidden rounded-full bg-buddy-border/40">
              <div
                className="h-full rounded-full bg-buddy-primary transition-all"
                style={{ width: `${(stage.value / max) * 100}%` }}
              />
            </div>
            <span className="w-8 shrink-0 text-right text-xs font-medium text-buddy-text-primary">
              {stage.value}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

import { Card } from "@/components/ui/Card";
import type { AnalyticsOverview } from "@/lib/types";

/**
 * Phase 6E Part 4 — deterministic, neutrally-worded counts. Every label
 * here is a literal record count, never "performance." No card on this
 * page ever ranks or scores an employee.
 */
export function OverviewCards({ overview }: { overview: AnalyticsOverview }) {
  const metrics: { label: string; value: number }[] = [
    { label: "Published Quests", value: overview.published_quests },
    { label: "Employees reached", value: overview.employees_reached },
    { label: "Quest attempts", value: overview.attempts_total },
    { label: "Completed Quest attempts", value: overview.attempts_completed },
    { label: "Employees with capability evidence", value: overview.employees_with_capability_evidence },
    { label: "Capability observations", value: overview.capability_observations },
    { label: "Recommendations generated", value: overview.recommendations_generated },
    { label: "Employees with development history", value: overview.employees_with_development_history },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {metrics.map((metric) => (
        <Card key={metric.label} className="text-center">
          <p className="font-heading text-2xl font-bold text-buddy-navy">{metric.value}</p>
          <p className="mt-1 text-xs text-buddy-muted">{metric.label}</p>
        </Card>
      ))}
    </div>
  );
}

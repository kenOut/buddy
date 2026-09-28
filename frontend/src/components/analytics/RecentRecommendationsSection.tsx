import Link from "next/link";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import type { RecentRecommendationItem } from "@/lib/types";

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

/**
 * Phase 6E Part 13 — "Quest X was recommended 7 times" is a fact about
 * Buddy's recommendation activity, never "Quest X is the best Quest."
 * A recommendation is not an assignment and not a completion — this
 * list only shows that a recommendation happened, not what came of it
 * (see Quest Activity above for completion data).
 */
export function RecentRecommendationsSection({
  recommendations,
}: {
  recommendations: RecentRecommendationItem[];
}) {
  if (recommendations.length === 0) {
    return (
      <Card>
        <p className="text-sm text-buddy-muted">
          No development recommendations have been generated yet.
        </p>
      </Card>
    );
  }

  return (
    <Card className="p-0">
      <ul>
        {recommendations.map((rec) => (
          <li
            key={rec.recommendation_id}
            className="flex flex-wrap items-center justify-between gap-3 border-b border-buddy-border px-6 py-3 text-sm last:border-0"
          >
            <div>
              <p className="text-buddy-text-primary">
                <Link href={`/admin/employees/${rec.employee_id}`} className="font-medium hover:text-buddy-primary">
                  {rec.employee_name}
                </Link>{" "}
                was recommended{" "}
                <Link href={`/admin/quests/${rec.quest_id}`} className="font-medium hover:text-buddy-primary">
                  {rec.quest_title}
                </Link>
              </p>
              <p className="mt-0.5 text-xs text-buddy-muted">{rec.reason}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {rec.target_capabilities.map((key) => (
                <Badge key={key} tone="info">
                  {key.replace(/_/g, " ")}
                </Badge>
              ))}
              <span className="text-xs text-buddy-muted">{formatDate(rec.created_at)}</span>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

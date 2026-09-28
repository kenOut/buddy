import Link from "next/link";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import type { BuddyState } from "@/components/buddy/buddyStates";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import type { CapabilityLevel, DevelopmentJourneyItem } from "@/lib/types";

const LEVEL_TONE: Record<CapabilityLevel, "neutral" | "info" | "success"> = {
  NOT_OBSERVED: "neutral",
  DEVELOPING: "neutral",
  CAPABLE: "info",
  STRONG: "success",
};

const ICON_BY_TYPE: Record<DevelopmentJourneyItem["type"], BuddyState> = {
  ONBOARDING_COMPLETED: "celebrating",
  QUEST_COMPLETED: "celebrating",
  CAPABILITY_OBSERVED: "encouraging",
  READINESS_REACHED: "success",
  WORKSPACE_ACCESS_GRANTED: "friendly",
  RECOMMENDATION: "guide",
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return iso;
  }
}

/**
 * One timeline entry. Every field it renders comes straight from the
 * employee-safe DevelopmentJourneyItem contract — there is nothing here
 * that could ever render a hidden evaluator field, because that data
 * never reaches this component's props in the first place.
 */
export function JourneyTimelineItem({
  item,
  isLast,
}: {
  item: DevelopmentJourneyItem;
  isLast: boolean;
}) {
  return (
    <li className="flex gap-3 sm:gap-4">
      <div className="flex shrink-0 flex-col items-center">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-buddy-primary/10">
          <span className="h-2.5 w-2.5 rounded-full bg-buddy-primary" aria-hidden="true" />
        </span>
        {!isLast && <span className="mt-1 w-px flex-1 bg-buddy-border/60" aria-hidden="true" />}
      </div>

      <Card className="mb-1 flex-1">
        <div className="flex items-start gap-3">
          <div className="h-8 w-8 shrink-0">
            <BuddyIllustration state={ICON_BY_TYPE[item.type]} />
          </div>
          <div className="flex-1">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
                {item.title}
              </p>
              <span className="text-xs text-buddy-muted">{formatDate(item.timestamp)}</span>
            </div>

            <p className="mt-1 text-sm text-buddy-text-primary">{item.description}</p>

            {item.type === "CAPABILITY_OBSERVED" && item.level && (
              <Badge tone={LEVEL_TONE[item.level]} className="mt-2">
                {item.level.toLowerCase()}
              </Badge>
            )}

            {item.type === "RECOMMENDATION" && (
              <>
                {item.reason && <p className="mt-2 text-sm text-buddy-text-secondary">{item.reason}</p>}
                {item.target_capabilities && item.target_capabilities.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {item.target_capabilities.map((key) => (
                      <Badge key={key} tone="info">
                        {key.replace(/_/g, " ")}
                      </Badge>
                    ))}
                  </div>
                )}
                {item.quest_id && (
                  <div className="mt-3">
                    {item.quest_available ? (
                      <Link
                        href={`/onboarding/quests/${item.quest_id}`}
                        className="text-sm font-medium text-buddy-primary hover:underline"
                      >
                        View this Quest →
                      </Link>
                    ) : (
                      <p className="text-xs text-buddy-muted">
                        This Quest is no longer available.
                      </p>
                    )}
                  </div>
                )}
              </>
            )}

            {item.type === "QUEST_COMPLETED" && item.quest_id && !item.quest_available && (
              <p className="mt-2 text-xs text-buddy-muted">This Quest is no longer available.</p>
            )}

            {item.type === "WORKSPACE_ACCESS_GRANTED" && item.workspace_link && (
              <div className="mt-3">
                <a
                  href={item.workspace_link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-medium text-buddy-primary hover:underline"
                >
                  Open {item.workspace_name ?? "workspace"} →
                </a>
              </div>
            )}
          </div>
        </div>
      </Card>
    </li>
  );
}

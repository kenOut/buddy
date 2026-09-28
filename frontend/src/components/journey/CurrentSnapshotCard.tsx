import { FadeIn } from "@/components/animations/FadeIn";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import type { CapabilityLevel, DevelopmentJourneyItem } from "@/lib/types";

const LEVEL_TONE: Record<CapabilityLevel, "neutral" | "info" | "success"> = {
  NOT_OBSERVED: "neutral",
  DEVELOPING: "neutral",
  CAPABLE: "info",
  STRONG: "success",
};

/**
 * Phase 8H-6 — "what have I demonstrated, what is still developing"
 * (the two questions this card exists to answer) requires more than a
 * single most-recent-observation line, so this now lists every distinct
 * capability with its own latest observed level. Still deliberately not
 * a score dashboard (Phase 6D Part 15): nothing here is a computed
 * rating — `level` is read as-is per CAPABILITY_OBSERVED item, exactly
 * as CapabilityInsight/JourneyTimelineItem already render it elsewhere,
 * just grouped down to one row per capability (its most recent
 * observation) instead of showing every individual event.
 */
export function CurrentSnapshotCard({ items }: { items: DevelopmentJourneyItem[] }) {
  const observed = items.filter((i) => i.type === "CAPABILITY_OBSERVED");

  const latestByCapability = new Map<string, DevelopmentJourneyItem>();
  for (const item of observed) {
    if (item.capability) latestByCapability.set(item.capability, item);
  }
  const capabilitySnapshots = [...latestByCapability.values()];

  return (
    <FadeIn duration={0.4}>
      <Card>
        <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
          Where you are now
        </p>
        <p className="mt-1 text-sm text-buddy-text-secondary">
          Every Quest you complete gives Buddy real evidence of what you can do — this is what
          it&rsquo;s seen so far.
        </p>

        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">
            What you&rsquo;ve demonstrated
          </p>
          {capabilitySnapshots.length === 0 ? (
            <p className="mt-2 text-sm text-buddy-text-secondary">
              Nothing yet — complete a Quest and Buddy will start showing what it&rsquo;s observed.
            </p>
          ) : (
            <div className="mt-2 flex flex-wrap gap-2">
              {capabilitySnapshots.map((item) => (
                <Badge key={item.capability} tone={item.level ? LEVEL_TONE[item.level] : "neutral"}>
                  {item.capability?.replace(/_/g, " ")}
                  {item.level ? ` — ${item.level.toLowerCase()}` : ""}
                </Badge>
              ))}
            </div>
          )}
        </div>
      </Card>
    </FadeIn>
  );
}

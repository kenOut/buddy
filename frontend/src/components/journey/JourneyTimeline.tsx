import { FadeIn } from "@/components/animations/FadeIn";
import type { DevelopmentJourneyItem } from "@/lib/types";
import { JourneyTimelineItem } from "./JourneyTimelineItem";

/**
 * A simple vertical timeline — a connecting line plus one card per
 * event, oldest first (matching the order the backend already sorted
 * items into; this component never re-sorts). Collapses naturally on
 * mobile since it's just a single column with no fixed widths.
 */
export function JourneyTimeline({ items }: { items: DevelopmentJourneyItem[] }) {
  if (items.length === 0) return null;

  return (
    <ol className="flex flex-col gap-0">
      {items.map((item, i) => (
        <FadeIn key={item.id} duration={0.35} delay={Math.min(i * 0.05, 0.4)}>
          <JourneyTimelineItem item={item} isLast={i === items.length - 1} />
        </FadeIn>
      ))}
    </ol>
  );
}

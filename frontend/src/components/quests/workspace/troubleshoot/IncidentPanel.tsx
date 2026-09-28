import { Card } from "@/components/ui/Card";
import type { EmployeeQuest } from "@/lib/types";

/**
 * The "Incident" phase — troubleshooting-flavored framing of exactly the
 * same `quest.description` GenericWorkspace's QuestChallenge already
 * renders. No new field: Stage 2's inspection confirmed there is no
 * dedicated incident-summary/impact/affected-area column on Quest, and
 * this panel does not fabricate one from unrelated fields — it only
 * changes the surrounding copy, not the underlying data.
 */
export function IncidentPanel({ quest }: { quest: EmployeeQuest }) {
  return (
    <Card>
      <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
        What&rsquo;s being reported
      </p>
      <p className="mt-2 text-sm text-buddy-text-primary">
        {quest.description ?? "Your manager hasn't added a description for this quest yet."}
      </p>
    </Card>
  );
}

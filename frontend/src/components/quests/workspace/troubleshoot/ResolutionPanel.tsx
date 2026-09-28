"use client";

import { Card } from "@/components/ui/Card";
import type { TroubleshootResolution } from "@/components/quests/workspace/troubleshootSubmissionAdapter";

/**
 * "Propose resolution" — deliberately minimal (Stage 2 §I): one required
 * field, one optional field. No mandatory mitigation/permanent-fix split
 * and no change-management workflow — those don't generalize past
 * production-incident domains, and the generic Troubleshoot Workspace
 * only asks what any troubleshooting domain actually needs to know.
 */
export function ResolutionPanel({
  resolution,
  onChange,
}: {
  resolution: TroubleshootResolution;
  onChange: (next: TroubleshootResolution) => void;
}) {
  return (
    <Card>
      <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">Proposed resolution</p>

      <div className="mt-3 space-y-3">
        <div>
          <label htmlFor="resolution-fix" className="mb-1.5 block text-sm font-medium text-buddy-text-primary">
            What would you do about it?
          </label>
          <textarea
            id="resolution-fix"
            value={resolution.proposed_fix}
            onChange={(e) => onChange({ ...resolution, proposed_fix: e.target.value })}
            rows={3}
            placeholder="What's your proposed fix?"
            className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm text-buddy-text-primary placeholder:text-buddy-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-buddy-primary"
          />
        </div>

        <div>
          <label htmlFor="resolution-validation" className="mb-1.5 block text-sm font-medium text-buddy-text-primary">
            How would you confirm it worked? <span className="font-normal text-buddy-muted">(optional)</span>
          </label>
          <textarea
            id="resolution-validation"
            value={resolution.validation_plan ?? ""}
            onChange={(e) => onChange({ ...resolution, validation_plan: e.target.value || null })}
            rows={2}
            placeholder="What would tell you this actually fixed it?"
            className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm text-buddy-text-primary placeholder:text-buddy-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-buddy-primary"
          />
        </div>
      </div>
    </Card>
  );
}

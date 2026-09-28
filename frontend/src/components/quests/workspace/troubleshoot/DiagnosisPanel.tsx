"use client";

import { Card } from "@/components/ui/Card";
import type { TroubleshootDiagnosis } from "@/components/quests/workspace/troubleshootSubmissionAdapter";

const CONFIDENCE_OPTIONS = ["Low", "Medium", "High"] as const;

/**
 * "Diagnose" — the employee's final committed explanation. Deliberately
 * NOT auto-filled from the strongest hypothesis (Stage 2 §H): a
 * hypothesis is a candidate, a diagnosis is a commitment, and conflating
 * them would lose the distinction the capability-evidence mapping (§K)
 * depends on. `confidence` is the employee's own stated read of their
 * certainty — never reinterpreted as an evaluation score, capability
 * level, or AI confidence.
 */
export function DiagnosisPanel({
  diagnosis,
  onChange,
}: {
  diagnosis: TroubleshootDiagnosis;
  onChange: (next: TroubleshootDiagnosis) => void;
}) {
  return (
    <Card>
      <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">Your diagnosis</p>
      <p className="mt-1 text-sm text-buddy-text-secondary">
        Based on what you&rsquo;ve investigated, what do you believe is the root cause?
      </p>

      <div className="mt-3 space-y-3">
        <div>
          <label htmlFor="diagnosis-root-cause" className="mb-1.5 block text-sm font-medium text-buddy-text-primary">
            Root cause
          </label>
          <textarea
            id="diagnosis-root-cause"
            value={diagnosis.root_cause}
            onChange={(e) => onChange({ ...diagnosis, root_cause: e.target.value })}
            rows={3}
            placeholder="What's actually causing this, and why?"
            className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm text-buddy-text-primary placeholder:text-buddy-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-buddy-primary"
          />
        </div>

        <div>
          <label htmlFor="diagnosis-confidence" className="mb-1.5 block text-sm font-medium text-buddy-text-primary">
            How confident are you?
          </label>
          <select
            id="diagnosis-confidence"
            value={diagnosis.confidence ?? ""}
            onChange={(e) => onChange({ ...diagnosis, confidence: e.target.value || null })}
            className="rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm text-buddy-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-buddy-primary"
          >
            <option value="">Not stated</option>
            {CONFIDENCE_OPTIONS.map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </div>
      </div>
    </Card>
  );
}

"use client";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import type { QuestTaskItem } from "@/lib/types";
import type { EvidenceRef, TroubleshootPayload } from "@/components/quests/workspace/troubleshootSubmissionAdapter";

/**
 * The Troubleshoot-specific review screen — replaces QuestReview's flat
 * three-field summary with the structured content (Stage 2 §14).
 * Structurally incapable of showing expected_answer/expected_behavior/
 * reference_solution/max_score/hidden criteria: nothing passed into this
 * component ever carries them (TroubleshootPayload has no such field,
 * same trust-boundary pattern as EmployeeQuestResponse elsewhere in this
 * codebase).
 *
 * The soft completeness hints below are guidance only — `canSubmit` is
 * computed entirely by the Engine from the legacy fields it already
 * validates; this component never disables Submit beyond that prop, per
 * the Stage 3 contract's explicit instruction not to invent a
 * frontend-only blocking rule.
 */
export function TroubleshootReview({
  payload,
  evidence,
  requiredTasks,
  completedIds,
  onSubmit,
  submitting,
  submitError,
  canSubmit,
}: {
  payload: TroubleshootPayload;
  evidence: EvidenceRef[];
  requiredTasks: QuestTaskItem[];
  completedIds: Set<string>;
  onSubmit: () => void;
  submitting: boolean;
  submitError: string | null;
  canSubmit: boolean;
}) {
  const evidenceById = new Map(evidence.map((e) => [e.id, e]));
  const reviewedTitles = payload.evidence_reviewed
    .map((id) => evidenceById.get(id)?.title)
    .filter((title): title is string => Boolean(title));

  const hints: string[] = [];
  if (payload.hypotheses.length === 0) hints.push("You haven't recorded any hypotheses yet.");
  if (!payload.diagnosis.root_cause.trim()) hints.push("You haven't written a diagnosis yet.");
  if (!payload.resolution.proposed_fix.trim()) hints.push("You haven't proposed a resolution yet.");

  return (
    <div className="space-y-4">
      <Card>
        <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">Evidence reviewed</p>
        <p className="mt-1 text-sm text-buddy-text-primary">
          {reviewedTitles.length > 0 ? reviewedTitles.join(", ") : <span className="text-buddy-muted">None yet</span>}
        </p>

        {payload.observations.length > 0 && (
          <>
            <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-buddy-primary">Observations</p>
            <ul className="mt-1 list-inside list-disc text-sm text-buddy-text-primary">
              {payload.observations.map((o, i) => (
                <li key={i}>{o}</li>
              ))}
            </ul>
          </>
        )}
      </Card>

      <Card>
        <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">Hypotheses</p>
        {payload.hypotheses.length === 0 ? (
          <p className="mt-1 text-sm text-buddy-muted">None recorded</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {payload.hypotheses.map((h) => (
              <li key={h.id} className="text-sm">
                <p className="text-buddy-text-primary">{h.statement || <span className="text-buddy-muted">(no statement)</span>}</p>
                {h.reasoning && <p className="text-buddy-text-secondary">{h.reasoning}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">Diagnosis</p>
        <p className="mt-1 text-sm text-buddy-text-primary">
          {payload.diagnosis.root_cause || <span className="text-buddy-muted">Not recorded</span>}
        </p>
        {payload.diagnosis.confidence && (
          <p className="mt-1 text-xs text-buddy-muted">Stated confidence: {payload.diagnosis.confidence}</p>
        )}
      </Card>

      <Card>
        <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">Resolution</p>
        <p className="mt-1 text-sm text-buddy-text-primary">
          {payload.resolution.proposed_fix || <span className="text-buddy-muted">Not recorded</span>}
        </p>
        {payload.resolution.validation_plan && (
          <>
            <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-buddy-primary">
              Validation plan
            </p>
            <p className="mt-1 text-sm text-buddy-text-primary">{payload.resolution.validation_plan}</p>
          </>
        )}
      </Card>

      {requiredTasks.length > 0 && (
        <Card>
          <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">Required tasks</p>
          <ul className="mt-2 space-y-1 text-sm">
            {requiredTasks.map((task) => {
              const done = completedIds.has(task.id);
              return (
                <li key={task.id} className={done ? "text-emerald-700 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}>
                  <span aria-hidden="true">{done ? "✓ " : "○ "}</span>
                  {task.title}
                  {!done && <span className="sr-only"> — not yet completed</span>}
                </li>
              );
            })}
          </ul>
        </Card>
      )}

      {hints.length > 0 && (
        <p className="text-xs text-buddy-muted">{hints.join(" ")}</p>
      )}

      {submitError && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {submitError}
        </p>
      )}

      <Button onClick={onSubmit} disabled={!canSubmit || submitting} className="w-full">
        {submitting ? "Submitting…" : "Submit quest"}
      </Button>
      {!canSubmit && !submitting && (
        <p className="text-center text-xs text-buddy-muted">
          Complete the required tasks and record at least one of your findings before submitting.
        </p>
      )}
    </div>
  );
}

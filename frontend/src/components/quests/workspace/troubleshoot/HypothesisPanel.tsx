"use client";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import type { EvidenceRef, Hypothesis } from "@/components/quests/workspace/troubleshootSubmissionAdapter";

function newHypothesis(): Hypothesis {
  const id = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `hyp-${Date.now()}-${Math.random()}`;
  return { id, statement: "", reasoning: "", supporting_evidence_ids: [] };
}

/**
 * "Form a hypothesis" — the first genuinely new interactive Troubleshoot
 * component (Stage 2 §G, Option C: a structured container around
 * free-form prose). Employees can hold multiple candidate explanations
 * at once, revise or drop any of them; only the current state is kept —
 * no edit history, per the Stage 2 contract's explicit anti-surveillance
 * guidance.
 */
export function HypothesisPanel({
  hypotheses,
  evidence,
  onChange,
}: {
  hypotheses: Hypothesis[];
  evidence: EvidenceRef[];
  onChange: (next: Hypothesis[]) => void;
}) {
  const addHypothesis = () => onChange([...hypotheses, newHypothesis()]);

  const updateHypothesis = (id: string, patch: Partial<Hypothesis>) => {
    onChange(hypotheses.map((h) => (h.id === id ? { ...h, ...patch } : h)));
  };

  const removeHypothesis = (id: string) => {
    onChange(hypotheses.filter((h) => h.id !== id));
  };

  const toggleEvidence = (hypothesisId: string, evidenceId: string) => {
    const target = hypotheses.find((h) => h.id === hypothesisId);
    if (!target) return;
    const has = target.supporting_evidence_ids.includes(evidenceId);
    const next = has
      ? target.supporting_evidence_ids.filter((id) => id !== evidenceId)
      : [...target.supporting_evidence_ids, evidenceId];
    updateHypothesis(hypothesisId, { supporting_evidence_ids: next });
  };

  return (
    <div className="space-y-4">
      <p aria-live="polite" className="sr-only">
        {hypotheses.length} hypothesis{hypotheses.length === 1 ? "" : "es"} recorded.
      </p>

      {hypotheses.length === 0 && (
        <Card>
          <p className="text-sm text-buddy-muted">
            No hypotheses yet. What do you think might be causing this?
          </p>
        </Card>
      )}

      {hypotheses.map((hypothesis, i) => (
        <Card key={hypothesis.id}>
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
              Hypothesis {i + 1}
            </p>
            <button
              type="button"
              onClick={() => removeHypothesis(hypothesis.id)}
              className="rounded px-2 py-1 text-xs text-red-600 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-buddy-primary"
            >
              Remove
            </button>
          </div>

          <div className="mt-3 space-y-3">
            <div>
              <label
                htmlFor={`hypothesis-statement-${hypothesis.id}`}
                className="mb-1.5 block text-sm font-medium text-buddy-text-primary"
              >
                What do you think is happening?
              </label>
              <textarea
                id={`hypothesis-statement-${hypothesis.id}`}
                value={hypothesis.statement}
                onChange={(e) => updateHypothesis(hypothesis.id, { statement: e.target.value })}
                rows={2}
                placeholder="e.g. the recent change is the cause"
                className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm text-buddy-text-primary placeholder:text-buddy-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-buddy-primary"
              />
            </div>

            <div>
              <label
                htmlFor={`hypothesis-reasoning-${hypothesis.id}`}
                className="mb-1.5 block text-sm font-medium text-buddy-text-primary"
              >
                Why do you think that?
              </label>
              <textarea
                id={`hypothesis-reasoning-${hypothesis.id}`}
                value={hypothesis.reasoning}
                onChange={(e) => updateHypothesis(hypothesis.id, { reasoning: e.target.value })}
                rows={2}
                placeholder="What makes this plausible?"
                className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm text-buddy-text-primary placeholder:text-buddy-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-buddy-primary"
              />
            </div>

            {evidence.length > 0 && (
              <fieldset>
                <legend className="mb-1.5 text-sm font-medium text-buddy-text-primary">
                  Which evidence supports this?
                </legend>
                <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                  {evidence.map((item) => (
                    <label
                      key={item.id}
                      className="flex cursor-pointer items-center gap-1.5 text-sm text-buddy-text-secondary"
                    >
                      <input
                        type="checkbox"
                        checked={hypothesis.supporting_evidence_ids.includes(item.id)}
                        onChange={() => toggleEvidence(hypothesis.id, item.id)}
                        className="h-4 w-4 accent-[var(--buddy-primary)]"
                      />
                      {item.title}
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
          </div>
        </Card>
      ))}

      <Button variant="secondary" onClick={addHypothesis}>
        + Add a hypothesis
      </Button>
    </div>
  );
}

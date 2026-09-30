"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { QuestBuddy, type QuestBuddyPhase } from "@/components/quests/QuestBuddy";
import { QuestHeader } from "@/components/quests/QuestHeader";
import { QuestTaskList } from "@/components/quests/QuestTaskList";
import { DiagnosisPanel } from "./troubleshoot/DiagnosisPanel";
import { EvidenceExplorer } from "./troubleshoot/EvidenceExplorer";
import { HypothesisPanel } from "./troubleshoot/HypothesisPanel";
import { IncidentPanel } from "./troubleshoot/IncidentPanel";
import { ObservePanel } from "./troubleshoot/ObservePanel";
import { ResolutionPanel } from "./troubleshoot/ResolutionPanel";
import { PHASE_ORDER, TroubleshootProgress, type TroubleshootPhase } from "./troubleshoot/TroubleshootProgress";
import { TroubleshootReview } from "./troubleshoot/TroubleshootReview";
import {
  evidenceRefsFromQuest,
  fromSubmission,
  toSubmission,
  type Hypothesis,
  type TroubleshootDiagnosis,
  type TroubleshootPayload,
  type TroubleshootResolution,
} from "./troubleshootSubmissionAdapter";
import type { WorkspaceProps } from "./types";

const PHASE_TO_BUDDY: Record<TroubleshootPhase, QuestBuddyPhase> = {
  "incident-view": "entry",
  investigating: "evidence",
  hypothesizing: "work",
  diagnosing: "work",
  resolving: "work",
  reviewing: "review",
};

/**
 * The real Troubleshooting Workspace (Phase 7 Stage 3) — replaces the
 * Stage 1 placeholder. Everything about the attempt itself (loading,
 * lifecycle, autosave, submit, evaluation, capability insight,
 * completion, recommendation) still lives entirely in the Engine
 * (useWorkspaceEngine) and QuestWorkspace.tsx's QuestEvaluationFlow —
 * neither of which this component touches. This workspace only owns:
 * its own internal phase navigation, its structured Troubleshoot state,
 * and translating that state into the two calls the Workspace contract
 * already provides (`onFieldChange`, `onWorkspacePayloadChange`) — it
 * never calls a Quest/QuestAttempt API function directly.
 */
export function TroubleshootWorkspace({
  context,
  lifecycle,
  draft,
  saveState,
  submitError,
  canSubmit,
  requiredTasks,
  onFieldChange,
  onWorkspacePayloadChange,
  onCompleteTask,
  onRetrySave,
  onSubmit,
}: WorkspaceProps) {
  const { quest } = context;
  const [phase, setPhase] = useState<TroubleshootPhase>("incident-view");
  // Lazy-initialized once, from whatever the Engine already restored into
  // draft.workspacePayload — after mount this local state is the source
  // of truth, exactly like GenericWorkspace's findings/reasoning/solution.
  const [payload, setPayload] = useState<TroubleshootPayload>(() => fromSubmission(draft.workspacePayload));

  const evidenceRefs = evidenceRefsFromQuest(quest.evidence);

  /**
   * The single write path every panel below goes through. Always
   * receives the FULL next payload (never a partial patch) — ­­­because
   * `onWorkspacePayloadChange` does a full-replace PATCH, a caller that
   * sent only `{ hypotheses }` would silently erase a previously-saved
   * diagnosis/resolution/evidence_reviewed. Also synthesizes and mirrors
   * the legacy findings/reasoning/solution fields on every change, per
   * the evaluation adapter design — the existing evaluator never sees an
   * empty submission just because this Workspace is structured
   * differently from Generic's.
   */
  const commit = (next: TroubleshootPayload) => {
    setPayload(next);
    onWorkspacePayloadChange(next as unknown as Record<string, unknown>);
    const legacy = toSubmission(next, evidenceRefs);
    onFieldChange("findings", legacy.findings);
    onFieldChange("reasoning", legacy.reasoning);
    onFieldChange("solution", legacy.solution);
  };

  const toggleEvidenceReviewed = (evidenceId: string) => {
    const has = payload.evidence_reviewed.includes(evidenceId);
    commit({
      ...payload,
      evidence_reviewed: has
        ? payload.evidence_reviewed.filter((id) => id !== evidenceId)
        : [...payload.evidence_reviewed, evidenceId],
    });
  };

  const handleHypothesesChange = (hypotheses: Hypothesis[]) => commit({ ...payload, hypotheses });
  const handleDiagnosisChange = (diagnosis: TroubleshootDiagnosis) => commit({ ...payload, diagnosis });
  const handleResolutionChange = (resolution: TroubleshootResolution) => commit({ ...payload, resolution });

  const buddyPhase: QuestBuddyPhase = lifecycle === "submitting" ? "submitting" : PHASE_TO_BUDDY[phase];
  const phaseIndex = PHASE_ORDER.indexOf(phase);

  return (
    <div className="flex flex-col gap-6">
      <QuestHeader quest={quest} />
      <QuestBuddy phase={buddyPhase} />
      <TroubleshootProgress current={phase} onJump={setPhase} />
      <SaveIndicator saveState={saveState} onRetry={onRetrySave} />

      <div aria-live="polite">
        {phase === "incident-view" && <IncidentPanel quest={quest} />}

        {phase === "investigating" && (
          <div className="space-y-4">
            <ObservePanel evidence={quest.evidence} />
            {quest.tasks.length > 0 && (
              <div className="rounded-2xl border border-buddy-border bg-buddy-surface p-6 shadow-sm">
                <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-buddy-primary">
                  Investigation tasks
                </p>
                <QuestTaskList tasks={quest.tasks} completedIds={draft.completedTaskIds} onToggle={onCompleteTask} />
              </div>
            )}
            <div className="rounded-2xl border border-buddy-border bg-buddy-surface p-6 shadow-sm">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-buddy-primary">Evidence</p>
              <EvidenceExplorer
                evidence={quest.evidence}
                reviewedIds={new Set(payload.evidence_reviewed)}
                onToggleReviewed={toggleEvidenceReviewed}
              />
            </div>
          </div>
        )}

        {phase === "hypothesizing" && (
          <HypothesisPanel hypotheses={payload.hypotheses} evidence={evidenceRefs} onChange={handleHypothesesChange} />
        )}

        {phase === "diagnosing" && <DiagnosisPanel diagnosis={payload.diagnosis} onChange={handleDiagnosisChange} />}

        {phase === "resolving" && (
          <ResolutionPanel resolution={payload.resolution} onChange={handleResolutionChange} />
        )}

        {phase === "reviewing" && (
          <TroubleshootReview
            payload={payload}
            evidence={evidenceRefs}
            requiredTasks={requiredTasks}
            completedIds={draft.completedTaskIds}
            onSubmit={onSubmit}
            submitting={lifecycle === "submitting"}
            submitError={submitError}
            canSubmit={canSubmit}
          />
        )}
      </div>

      <div className="flex items-center justify-between">
        <Button
          variant="secondary"
          disabled={phase === "incident-view"}
          onClick={() => {
            if (phaseIndex > 0) setPhase(PHASE_ORDER[phaseIndex - 1]);
          }}
        >
          Back
        </Button>
        {phase !== "reviewing" && (
          <Button
            onClick={() => {
              if (phaseIndex < PHASE_ORDER.length - 1) setPhase(PHASE_ORDER[phaseIndex + 1]);
            }}
          >
            Continue →
          </Button>
        )}
      </div>
    </div>
  );
}

function SaveIndicator({ saveState, onRetry }: { saveState: WorkspaceProps["saveState"]; onRetry: () => void }) {
  if (saveState === "idle") return null;
  return (
    <p aria-live="polite" className="flex items-center gap-2 text-xs text-buddy-muted">
      {saveState === "saving" && "Saving…"}
      {saveState === "saved" && "Saved"}
      {saveState === "error" && (
        <span role="alert" className="flex items-center gap-2 text-red-600 dark:text-red-400">
          Save failed
          <button
            type="button"
            onClick={onRetry}
            className="font-medium underline underline-offset-2 hover:text-red-700 dark:hover:text-red-400"
          >
            Retry
          </button>
        </span>
      )}
    </p>
  );
}

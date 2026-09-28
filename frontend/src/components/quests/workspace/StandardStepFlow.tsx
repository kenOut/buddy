"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { QuestBuddy, type QuestBuddyPhase } from "@/components/quests/QuestBuddy";
import { QuestChallenge } from "@/components/quests/QuestChallenge";
import { QuestEvidencePanel } from "@/components/quests/QuestEvidencePanel";
import { QuestProgressSteps, STEP_ORDER, type QuestStep } from "@/components/quests/QuestProgressSteps";
import { QuestReview } from "@/components/quests/QuestReview";
import { QuestTaskList } from "@/components/quests/QuestTaskList";
import { QuestWorkForm } from "@/components/quests/QuestWorkForm";
import type { WorkspaceProps } from "./types";

/**
 * The challenge/evidence/tasks/work/review step flow, factored out of
 * GenericWorkspace so TroubleshootWorkspace's placeholder can reuse it
 * verbatim underneath its "coming soon" banner (Stage 1's placeholder
 * has no specialized interaction of its own yet — see TroubleshootWorkspace.tsx).
 * Not exported outside this module: it's an implementation detail shared
 * between two registry entries, not a third public Workspace API.
 */
export function StandardStepFlow({
  context,
  lifecycle,
  draft,
  saveState,
  submitError,
  canSubmit,
  requiredTasks,
  onFieldChange,
  onCompleteTask,
  onRetrySave,
  onSubmit,
}: WorkspaceProps) {
  const { quest } = context;
  const [step, setStep] = useState<QuestStep>("challenge");

  const buddyPhase: QuestBuddyPhase =
    lifecycle === "submitting"
      ? "submitting"
      : step === "challenge"
        ? "entry"
        : step === "evidence"
          ? "evidence"
          : step === "work"
            ? "work"
            : "review";

  return (
    <>
      <QuestBuddy phase={buddyPhase} />
      <QuestProgressSteps current={step} onJump={setStep} />

      <div aria-live="polite">
        {step === "challenge" && <QuestChallenge quest={quest} />}

        {step === "evidence" && (
          <Card>
            <QuestEvidencePanel evidence={quest.evidence} />
          </Card>
        )}

        {step === "work" && (
          <div className="space-y-4">
            {quest.tasks.length > 0 && (
              <Card>
                <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-buddy-primary">
                  Tasks
                </p>
                <QuestTaskList tasks={quest.tasks} completedIds={draft.completedTaskIds} onToggle={onCompleteTask} />
              </Card>
            )}
            <Card>
              <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-buddy-primary">
                Record your work
              </p>
              <QuestWorkForm
                findings={draft.findings}
                reasoning={draft.reasoning}
                solution={draft.solution}
                onChange={onFieldChange}
                saveState={saveState}
                onRetry={onRetrySave}
              />
            </Card>
          </div>
        )}

        {step === "review" && (
          <QuestReview
            submission={{ findings: draft.findings, reasoning: draft.reasoning, solution: draft.solution }}
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
          disabled={step === "challenge"}
          onClick={() => {
            const i = STEP_ORDER.indexOf(step);
            if (i > 0) setStep(STEP_ORDER[i - 1]);
          }}
        >
          Back
        </Button>
        {step !== "review" && (
          <Button
            onClick={() => {
              const i = STEP_ORDER.indexOf(step);
              if (i < STEP_ORDER.length - 1) setStep(STEP_ORDER[i + 1]);
            }}
          >
            Continue →
          </Button>
        )}
      </div>
    </>
  );
}

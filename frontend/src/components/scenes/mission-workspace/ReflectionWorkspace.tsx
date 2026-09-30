"use client";

import { useRef, useState } from "react";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { BuddySpeech } from "@/components/buddy/BuddySpeech";
import { FadeIn } from "@/components/animations/FadeIn";
import { SlideUp } from "@/components/animations/SlideUp";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ApiError } from "@/lib/api";
import { submitMissionAttempt } from "@/lib/missionAttempts";
import type { MissionAssignment, MissionAttempt, MissionType } from "@/lib/types";
import { CapabilityInsight } from "./CapabilityInsight";

interface ReflectionWorkspaceProps {
  assignment: MissionAssignment;
  attempt: MissionAttempt;
  employeeId: string;
  onSubmitted: (attempt: MissionAttempt) => void;
}

const MIN_REFLECTION_LENGTH = 40;

/** What to actually ask for, per mission_type — the same freeform field
 * (MissionAttempt.reasoning) backs all of them; only the prompt changes,
 * so the work asked for is true to what the mission actually is. */
const PROMPT_BY_TYPE: Record<MissionType, string> = {
  setup: "What did you set up, and what confirms it's actually working?",
  meeting: "What's one thing you learned from this conversation?",
  training: "Summarize the most important things you took from this.",
  reading: "What are the key things you took away from this?",
  task: "Describe what you shipped and how you verified it.",
};

/**
 * The "reflection" workspace_type — a real freeform submission, not a
 * bare "mark as complete" click. There's no objectively correct answer
 * to grade, so completion is gated on a real-effort length bar
 * (mission_attempt_service._grade_reflection); once that clears, the
 * same AI provider Quests and investigation Missions already use reads
 * the submission live and surfaces a genuine capability insight
 * (CapabilityInsight — identical component, just fed from here).
 */
export function ReflectionWorkspace({ assignment, attempt: initialAttempt, employeeId, onSubmitted }: ReflectionWorkspaceProps) {
  const [attempt, setAttempt] = useState(initialAttempt);
  const [reasoning, setReasoning] = useState(initialAttempt.reasoning ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const submittingRef = useRef(false);

  const isReadOnly = attempt.status === "completed";
  const hasResult = attempt.status === "submitted" || attempt.status === "completed";
  const trimmedLength = reasoning.trim().length;
  const canSubmit = trimmedLength >= MIN_REFLECTION_LENGTH;
  const prompt = PROMPT_BY_TYPE[assignment.mission.mission_type];

  const submit = async () => {
    if (submittingRef.current || !canSubmit) return;
    submittingRef.current = true;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const result = await submitMissionAttempt(attempt.id, {
        employee_id: employeeId,
        reasoning,
      });
      setAttempt(result);
      onSubmitted(result);
    } catch (err) {
      setSubmitError(
        err instanceof ApiError
          ? "Couldn't submit your work. Please try again."
          : "Network error — couldn't reach the server. Please try again."
      );
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="font-heading text-xl font-bold text-buddy-navy sm:text-2xl">
          {assignment.mission.title}
        </h1>
        <div className="flex items-center gap-2">
          {assignment.mission.required && <Badge tone="coral">Required for readiness</Badge>}
          <Badge tone={attempt.status === "completed" ? "success" : "info"}>
            {attempt.status.replace("_", " ")}
          </Badge>
        </div>
      </div>

      <FadeIn duration={0.4} className="flex items-start gap-3">
        <div className="h-12 w-12 shrink-0">
          <BuddyIllustration
            state={hasResult ? (attempt.passed ? "success" : "encouraging") : "guide"}
          />
        </div>
        <BuddySpeech className="flex-1 py-2.5">
          <p className="text-sm text-buddy-text-secondary">
            {assignment.mission.description}
          </p>
        </BuddySpeech>
      </FadeIn>

      <div aria-live="polite">{hasResult && <ReflectionResultCard attempt={attempt} />}</div>

      {attempt.passed && <CapabilityInsight attemptId={attempt.id} employeeId={employeeId} />}

      <Card>
        <label htmlFor="reflection-text" className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">
          {prompt}
        </label>
        <textarea
          id="reflection-text"
          value={reasoning}
          onChange={(e) => setReasoning(e.target.value)}
          disabled={isReadOnly}
          rows={5}
          placeholder="Write a real, specific answer — a couple of sentences is plenty."
          className="mt-2 w-full rounded-lg border border-buddy-border bg-buddy-surface p-3 text-sm text-buddy-text-primary focus:border-buddy-primary focus:outline-none disabled:opacity-70"
        />
        {!isReadOnly && (
          <p className="mt-1 text-right text-xs text-buddy-muted">
            {trimmedLength}/{MIN_REFLECTION_LENGTH} characters
          </p>
        )}
      </Card>

      {!isReadOnly && (
        <Card>
          {submitError && (
            <p role="alert" className="mb-3 text-sm text-red-600 dark:text-red-400">
              {submitError}
            </p>
          )}
          <Button onClick={submit} disabled={!canSubmit || submitting} className="w-full">
            {submitting ? "Submitting…" : hasResult ? "Resubmit" : "Submit"}
          </Button>
          {!canSubmit && (
            <p className="mt-2 text-center text-xs text-buddy-muted">
              Add a bit more detail to submit — real specifics, not just &ldquo;done.&rdquo;
            </p>
          )}
        </Card>
      )}
    </div>
  );
}

function ReflectionResultCard({ attempt }: { attempt: MissionAttempt }) {
  return (
    <SlideUp duration={0.35}>
      <Card className={attempt.passed ? "border-buddy-aurora/40 bg-buddy-aurora/5" : undefined}>
        <p className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">
          {attempt.passed ? "Mission complete" : "Not quite yet"}
        </p>
        {attempt.feedback && <p className="mt-2 text-sm text-buddy-text-primary">{attempt.feedback}</p>}
      </Card>
    </SlideUp>
  );
}

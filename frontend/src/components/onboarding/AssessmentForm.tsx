"use client";

import { useState } from "react";
import { motion } from "motion/react";
import clsx from "clsx";

import { ProgressAnimation } from "@/components/animations/ProgressAnimation";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { useOnboarding } from "@/lib/onboarding-context";
import { nextScene } from "@/lib/scenes";
import type { Assessment, AssessmentQuestion } from "@/lib/types";

/** Never shaming — every band is framed as encouragement or support. */
function readinessCopy(score: number): string {
  if (score >= 90) return "Strong across the board — you're ready to move on.";
  if (score >= 75) return "Solid grasp already. A couple of things to revisit as you go.";
  return "A good starting point — your buddy will walk through the rest with you.";
}

export function AssessmentForm({
  questions,
  sessionId,
  employeeId,
  onResult,
}: {
  questions: AssessmentQuestion[];
  sessionId: string;
  employeeId: string;
  onResult?: (assessment: Assessment) => void;
}) {
  const { goToScene } = useOnboarding();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<Assessment | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const allAnswered = questions.every((q) => answers[q.id]);

  const submit = async () => {
    // Guards against duplicate submissions from a double-click/double-tap,
    // in addition to the button's own `disabled={submitting}`.
    if (submitting) return;

    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        onboarding_session_id: sessionId,
        employee_id: employeeId,
        answers: Object.entries(answers).map(([question_id, selected_option]) => ({
          question_id,
          selected_option,
        })),
      };
      const assessment = await api.post<Assessment>("/onboarding/assessments", payload);
      setResult(assessment);
      onResult?.(assessment);
    } catch {
      // `submitting` is always reset in `finally` below, so the button
      // re-enables and the user can retry — it never gets stuck.
      setError("We couldn't submit your assessment. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (result) {
    const next = nextScene("assessment");
    const score = result.score ?? 0;
    return (
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="space-y-6"
      >
        <div className="text-center">
          <p className="text-xs font-semibold uppercase tracking-widest text-buddy-primary">
            Readiness
          </p>
          <p className="font-heading mt-1 text-5xl font-bold text-buddy-navy">{score}%</p>
        </div>

        <ProgressAnimation percent={score} height={10} />

        <p className="text-center text-sm text-buddy-text-secondary">{readinessCopy(score)}</p>

        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-buddy-muted">
            Areas assessed
          </p>
          <ul className="space-y-1.5">
            {questions.map((q) => (
              <li
                key={q.id}
                className="flex items-center gap-2 rounded-lg bg-buddy-cloud px-3 py-2 text-sm text-buddy-text-primary"
              >
                <span className="text-buddy-aurora" aria-hidden="true">
                  ✓
                </span>
                {q.prompt}
              </li>
            ))}
          </ul>
        </div>

        {next && (
          <div className="flex justify-center">
            <Button onClick={() => goToScene(next.key)}>Continue to {next.short}</Button>
          </div>
        )}
      </motion.div>
    );
  }

  return (
    <div className="space-y-6">
      {questions.map((question) => (
        <fieldset key={question.id}>
          <legend className="mb-2 text-sm font-medium text-foreground">{question.prompt}</legend>
          <div className="space-y-2">
            {question.options.map((option) => (
              <label
                key={option.id}
                className={clsx(
                  "flex cursor-pointer items-center gap-3 rounded-lg border border-buddy-border px-3 py-2 text-sm transition-colors",
                  answers[question.id] === option.id
                    ? "border-buddy-primary bg-buddy-primary/5"
                    : "hover:border-buddy-primary/40"
                )}
              >
                <input
                  type="radio"
                  name={question.id}
                  value={option.id}
                  checked={answers[question.id] === option.id}
                  onChange={() => setAnswers((prev) => ({ ...prev, [question.id]: option.id }))}
                  className="accent-[var(--buddy-primary)]"
                />
                {option.label}
              </label>
            ))}
          </div>
        </fieldset>
      ))}

      {error && (
        <p
          role="alert"
          className="rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/30 px-3 py-2 text-sm text-red-600 dark:text-red-400"
        >
          {error}
        </p>
      )}

      <Button onClick={submit} disabled={!allAnswered || submitting} className="w-full">
        {submitting ? "Submitting…" : "Submit assessment"}
      </Button>
    </div>
  );
}

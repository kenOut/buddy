"use client";

import { useRef, useState } from "react";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { BuddySpeech } from "@/components/buddy/BuddySpeech";
import { FadeIn } from "@/components/animations/FadeIn";
import { SlideUp } from "@/components/animations/SlideUp";
import { ProgressAnimation } from "@/components/animations/ProgressAnimation";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ApiError } from "@/lib/api";
import { submitMissionAttempt } from "@/lib/missionAttempts";
import type { MissionAssignment, MissionAttempt, MissionQuiz } from "@/lib/types";

interface QuizWorkspaceProps {
  assignment: MissionAssignment;
  quiz: MissionQuiz;
  attempt: MissionAttempt;
  employeeId: string;
  onSubmitted: (attempt: MissionAttempt) => void;
}

/**
 * The "quiz" workspace_type — a real comprehension check with an
 * objectively right answer, graded deterministically the moment it's
 * submitted (mission_quizzes.grade). Deliberately no AI read afterward:
 * a multiple-choice pass/fail has nothing qualitative left to interpret
 * (see Mission.workspace_type's own backend docstring) — "evaluated
 * live" here means the grade appears the instant you submit, not that
 * an AI narrates it.
 */
export function QuizWorkspace({ assignment, quiz, attempt: initialAttempt, employeeId, onSubmitted }: QuizWorkspaceProps) {
  const [attempt, setAttempt] = useState(initialAttempt);
  const [answers, setAnswers] = useState<Record<string, string>>(initialAttempt.quiz_answers ?? {});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const submittingRef = useRef(false);

  const isReadOnly = attempt.status === "completed";
  const hasResult = attempt.score != null;
  const answeredCount = quiz.questions.filter((q) => !!answers[q.id]).length;
  const canSubmit = answeredCount === quiz.questions.length;

  const selectAnswer = (questionId: string, option: string) => {
    if (isReadOnly) return;
    setAnswers((prev) => ({ ...prev, [questionId]: option }));
  };

  const submit = async () => {
    if (submittingRef.current || !canSubmit) return;
    submittingRef.current = true;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const result = await submitMissionAttempt(attempt.id, {
        employee_id: employeeId,
        quiz_answers: answers,
      });
      setAttempt(result);
      onSubmitted(result);
    } catch (err) {
      setSubmitError(
        err instanceof ApiError
          ? "Couldn't submit your answers. Please try again."
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
          <BuddyIllustration state={hasResult ? (attempt.passed ? "success" : "encouraging") : "guide"} />
        </div>
        <BuddySpeech className="flex-1 py-2.5">
          <p className="text-sm text-buddy-text-secondary">{quiz.briefing}</p>
        </BuddySpeech>
      </FadeIn>

      <div aria-live="polite">{hasResult && <QuizResultCard attempt={attempt} total={quiz.questions.length} />}</div>

      <div className="flex flex-col gap-4">
        {quiz.questions.map((question, index) => (
          <Card key={question.id}>
            <p className="text-sm font-semibold text-buddy-text-primary">
              {index + 1}. {question.prompt}
            </p>
            <div className="mt-3 flex flex-col gap-2">
              {question.options.map((option) => {
                const selected = answers[question.id] === option;
                return (
                  <label
                    key={option}
                    className={`flex cursor-pointer items-start gap-2 rounded-lg border p-3 text-sm transition-colors ${
                      selected
                        ? "border-buddy-primary bg-buddy-primary/5 text-buddy-navy"
                        : "border-buddy-border text-buddy-text-secondary hover:border-buddy-primary/40"
                    } ${isReadOnly ? "cursor-not-allowed opacity-70" : ""}`}
                  >
                    <input
                      type="radio"
                      name={question.id}
                      className="mt-0.5"
                      checked={selected}
                      disabled={isReadOnly}
                      onChange={() => selectAnswer(question.id, option)}
                    />
                    <span>{option}</span>
                  </label>
                );
              })}
            </div>
          </Card>
        ))}
      </div>

      {!isReadOnly && (
        <Card>
          {submitError && (
            <p role="alert" className="mb-3 text-sm text-red-600">
              {submitError}
            </p>
          )}
          <Button onClick={submit} disabled={!canSubmit || submitting} className="w-full">
            {submitting ? "Grading…" : hasResult ? "Resubmit answers" : "Submit answers"}
          </Button>
          {!canSubmit && (
            <p className="mt-2 text-center text-xs text-buddy-muted">
              Answer all {quiz.questions.length} questions to submit ({answeredCount} of{" "}
              {quiz.questions.length} answered).
            </p>
          )}
        </Card>
      )}
    </div>
  );
}

function QuizResultCard({ attempt, total }: { attempt: MissionAttempt; total: number }) {
  return (
    <SlideUp duration={0.35}>
      <Card className={attempt.passed ? "border-buddy-aurora/40 bg-buddy-aurora/5" : undefined}>
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">
            {attempt.passed ? "Quiz complete" : "Last submission"}
          </p>
          <p className="font-heading text-2xl font-bold text-buddy-navy">{attempt.score}%</p>
        </div>
        <ProgressAnimation percent={attempt.score ?? 0} height={6} className="mt-3" />
        {attempt.feedback && <p className="mt-3 text-sm text-buddy-text-primary">{attempt.feedback}</p>}
        {!attempt.passed && (
          <p className="mt-2 text-xs text-buddy-muted">Review the questions above and try again.</p>
        )}
        {attempt.passed && (
          <p className="mt-2 text-xs text-buddy-muted">All {total} questions correct.</p>
        )}
      </Card>
    </SlideUp>
  );
}

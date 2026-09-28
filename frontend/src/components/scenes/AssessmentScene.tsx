"use client";

import { useState } from "react";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import type { BuddyState } from "@/components/buddy/buddyStates";
import { BuddySpeech } from "@/components/buddy/BuddySpeech";
import { AssessmentForm } from "@/components/onboarding/AssessmentForm";
import { useOnboarding } from "@/lib/onboarding-context";
import type { Assessment } from "@/lib/types";

export function AssessmentScene() {
  const { bundle } = useOnboarding();
  const [buddyState, setBuddyState] = useState<BuddyState>("thinking");
  const [intro, setIntro] = useState(true);

  if (!bundle) return null;

  const handleResult = (assessment: Assessment) => {
    setBuddyState(assessment.passed ? "success" : "encouraging");
    setIntro(false);
  };

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-8 py-4">
      <div className="flex items-start gap-3 sm:gap-4">
        <div className="h-16 w-16 shrink-0">
          <BuddyIllustration state={buddyState} />
        </div>
        <BuddySpeech className="flex-1">
          {intro ? (
            <>
              <p className="font-heading text-lg font-bold text-buddy-navy">
                A quick capability check
              </p>
              <p className="mt-1 text-buddy-text-secondary">
                A handful of questions about how the team works day to day — there&rsquo;s no
                failing here, just a starting point.
              </p>
            </>
          ) : (
            <p className="text-buddy-text-secondary">
              {buddyState === "success"
                ? "Great instincts — that'll serve you well here."
                : "That's exactly what onboarding is for. You've got support."}
            </p>
          )}
        </BuddySpeech>
      </div>

      <AssessmentForm
        questions={bundle.assessment_questions}
        sessionId={bundle.session.id}
        employeeId={bundle.employee.id}
        onResult={handleResult}
      />
    </div>
  );
}

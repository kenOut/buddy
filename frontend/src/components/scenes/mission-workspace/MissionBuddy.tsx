"use client";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import type { BuddyState } from "@/components/buddy/buddyStates";
import { BuddySpeech } from "@/components/buddy/BuddySpeech";
import { FadeIn } from "@/components/animations/FadeIn";

export type MissionBuddyPhase = "opening" | "investigating" | "submitting" | "success" | "encouraging";

const PHASE_CONFIG: Record<MissionBuddyPhase, { state: BuddyState; message: string }> = {
  opening: {
    state: "guide",
    message: "Take your time. Start by understanding what the evidence is telling you.",
  },
  investigating: {
    state: "focused",
    message: "Look for the signal that changed. Don't jump to a conclusion yet.",
  },
  submitting: {
    state: "thinking",
    message: "Let's see what your investigation tells us.",
  },
  success: {
    state: "success",
    message: "Nice work. You followed the evidence.",
  },
  encouraging: {
    state: "encouraging",
    message: "You're close. Make sure you've explained what evidence led you to your conclusion.",
  },
};

/**
 * One consistent Buddy presence for the whole workspace — only 5 fixed
 * beats (opening / investigating / submitting / success / encouraging),
 * each triggered by a real phase transition, not by every click. The
 * `key={phase}` means the fade-in only replays when the phase actually
 * changes, so Buddy isn't re-animating while the employee works.
 */
export function MissionBuddy({ phase }: { phase: MissionBuddyPhase }) {
  const { state, message } = PHASE_CONFIG[phase];

  return (
    <FadeIn key={phase} duration={0.4} className="flex items-start gap-3">
      <div className="h-12 w-12 shrink-0">
        <BuddyIllustration state={state} />
      </div>
      <BuddySpeech className="flex-1 py-2.5">
        <p className="text-sm text-buddy-text-secondary">{message}</p>
      </BuddySpeech>
    </FadeIn>
  );
}

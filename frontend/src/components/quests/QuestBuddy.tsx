"use client";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import type { BuddyState } from "@/components/buddy/buddyStates";
import { BuddySpeech } from "@/components/buddy/BuddySpeech";
import { FadeIn } from "@/components/animations/FadeIn";

/**
 * Covers everything up through the AI evaluation running. Once an
 * evaluation result exists, QuestCapabilityInsight takes over with its
 * own per-section Buddy accents (curious/encouraging/guide — the same
 * pattern Phase 3A's CapabilityInsight.tsx already established for
 * Mission), and QuestCompletion closes with "celebrating" — so this
 * component's job ends at "evaluating".
 */
export type QuestBuddyPhase = "entry" | "evidence" | "work" | "review" | "submitting" | "evaluating";

const PHASE_CONFIG: Record<QuestBuddyPhase, { state: BuddyState; message: string }> = {
  entry: {
    state: "guide",
    message: "Ready? Let's see what we're dealing with.",
  },
  evidence: {
    state: "curious",
    message: "Take your time. The evidence is there to help you form your own conclusion.",
  },
  work: {
    state: "focused",
    message: "Good. Now explain how you arrived at your conclusion.",
  },
  review: {
    state: "thinking",
    message: "Looks like you've done the work. Give it one more look before you submit.",
  },
  submitting: {
    state: "focused",
    message: "Sending this over…",
  },
  evaluating: {
    state: "thinking",
    message: "Give me a moment — I'm looking at how you worked through this.",
  },
};

/**
 * Mirrors MissionBuddy's exact pattern: a fixed set of phases, each with
 * one Buddy state and one line — no per-keystroke reactions. Buddy
 * guides the process here, never the answer (no phase references what
 * the "right" outcome is)."
 */
export function QuestBuddy({ phase }: { phase: QuestBuddyPhase }) {
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

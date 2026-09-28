"use client";

import clsx from "clsx";

export type QuestStep = "challenge" | "evidence" | "work" | "review";

export const STEP_ORDER: QuestStep[] = ["challenge", "evidence", "work", "review"];

const STEP_LABELS: { key: QuestStep; label: string }[] = [
  { key: "challenge", label: "Challenge" },
  { key: "evidence", label: "Evidence" },
  { key: "work", label: "Your Work" },
  { key: "review", label: "Submit" },
];

/** Not tied to any quest_type — the same four stages apply whether this
 * is an INVESTIGATE, BUILD, or DESIGN quest (Stage 4 spec §21: all types
 * share one generic workspace for now). */
export function QuestProgressSteps({
  current,
  onJump,
}: {
  current: QuestStep;
  onJump: (step: QuestStep) => void;
}) {
  const currentIndex = STEP_ORDER.indexOf(current);

  return (
    <div role="tablist" aria-label="Quest progress" className="flex items-center gap-1 sm:gap-2">
      {STEP_LABELS.map((step, i) => {
        const done = i < currentIndex;
        const active = i === currentIndex;
        const reachable = i <= currentIndex;
        return (
          <button
            key={step.key}
            type="button"
            role="tab"
            aria-selected={active}
            aria-current={active ? "step" : undefined}
            disabled={!reachable}
            onClick={() => reachable && onJump(step.key)}
            className={clsx(
              "flex-1 rounded-full px-2 py-2 text-center text-[11px] font-medium uppercase tracking-wide transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-buddy-primary sm:text-xs",
              active
                ? "bg-buddy-primary text-white"
                : done
                  ? "bg-buddy-aurora/15 text-emerald-700"
                  : "bg-buddy-border/40 text-buddy-muted",
              !reachable && "cursor-not-allowed opacity-60"
            )}
          >
            {step.label}
          </button>
        );
      })}
    </div>
  );
}

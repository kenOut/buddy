"use client";

import clsx from "clsx";

export type TroubleshootPhase =
  | "incident-view"
  | "investigating"
  | "hypothesizing"
  | "diagnosing"
  | "resolving"
  | "reviewing";

export const PHASE_ORDER: TroubleshootPhase[] = [
  "incident-view",
  "investigating",
  "hypothesizing",
  "diagnosing",
  "resolving",
  "reviewing",
];

const PHASE_LABELS: { key: TroubleshootPhase; label: string }[] = [
  { key: "incident-view", label: "Incident" },
  { key: "investigating", label: "Investigate" },
  { key: "hypothesizing", label: "Hypotheses" },
  { key: "diagnosing", label: "Diagnosis" },
  { key: "resolving", label: "Resolution" },
  { key: "reviewing", label: "Submit" },
];

/**
 * The Troubleshoot Workspace's own progress indicator — a distinct
 * component from QuestProgressSteps (Generic's four-step
 * challenge/evidence/work/review), because the sections themselves are
 * genuinely different, not a relabeling of the same four. Same
 * guided-sections-with-free-backward-navigation behavior though: this
 * mirrors QuestProgressSteps' `reachable = i <= currentIndex` rule
 * exactly, per the Stage 2 contract's explicit instruction to extend
 * that pattern's shape rather than invent a new one.
 */
export function TroubleshootProgress({
  current,
  onJump,
}: {
  current: TroubleshootPhase;
  onJump: (phase: TroubleshootPhase) => void;
}) {
  const currentIndex = PHASE_ORDER.indexOf(current);

  // Six sections (vs. Generic's four) don't fit one row at 390px without
  // either truncating labels or cramming them — this scrolls horizontally
  // within its own bounded track instead, a standard mobile tab-bar
  // pattern, rather than letting the six-item row force the whole page
  // to scroll sideways.
  return (
    <div
      role="tablist"
      aria-label="Troubleshooting progress"
      className="-mx-1 flex w-full max-w-full items-center gap-1 overflow-x-auto px-1 sm:gap-2"
    >
      {PHASE_LABELS.map((phase, i) => {
        const done = i < currentIndex;
        const active = i === currentIndex;
        const reachable = i <= currentIndex;
        return (
          <button
            key={phase.key}
            type="button"
            role="tab"
            aria-selected={active}
            aria-current={active ? "step" : undefined}
            disabled={!reachable}
            onClick={() => reachable && onJump(phase.key)}
            className={clsx(
              "shrink-0 rounded-full px-3 py-2 text-center text-[11px] font-medium uppercase tracking-wide transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-buddy-primary sm:text-xs",
              active
                ? "bg-buddy-primary text-white"
                : done
                  ? "bg-buddy-aurora/15 text-emerald-700 dark:text-emerald-400"
                  : "bg-buddy-border/40 text-buddy-muted",
              !reachable && "cursor-not-allowed opacity-60"
            )}
          >
            {phase.label}
          </button>
        );
      })}
    </div>
  );
}

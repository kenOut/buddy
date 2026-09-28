"use client";

import { motion, useReducedMotion } from "motion/react";
import clsx from "clsx";

interface ProgressAnimationProps {
  /** 0–100 */
  percent: number;
  className?: string;
  trackClassName?: string;
  barClassName?: string;
  /** Height in px for the bar; ignored if barClassName sets its own. */
  height?: number;
}

/**
 * A single animated progress bar primitive — used by the onboarding
 * ProgressIndicator, and reusable for any other percent-based meter
 * (e.g. an assessment readiness score) instead of re-implementing the
 * same width/spring animation twice.
 */
export function ProgressAnimation({
  percent,
  className,
  trackClassName,
  barClassName,
  height = 8,
}: ProgressAnimationProps) {
  const reduceMotion = useReducedMotion();
  const clamped = Math.min(100, Math.max(0, percent));

  return (
    <div
      className={clsx("w-full overflow-hidden rounded-full bg-buddy-border/70", trackClassName, className)}
      style={{ height }}
      role="progressbar"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <motion.div
        className={clsx("h-full rounded-full bg-buddy-primary", barClassName)}
        initial={false}
        animate={{ width: `${clamped}%` }}
        transition={
          reduceMotion
            ? { duration: 0.01 }
            : { type: "spring", stiffness: 120, damping: 20 }
        }
      />
    </div>
  );
}

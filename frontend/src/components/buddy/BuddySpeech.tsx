"use client";

import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";
import clsx from "clsx";

interface BuddySpeechProps {
  children: ReactNode;
  className?: string;
  /** Where the pointer/tail sits relative to the bubble. */
  tail?: "left" | "bottom";
}

/**
 * Buddy's dialogue — a clean, modern note rather than a cartoon speech
 * bubble, to stay in the "professional companion" register rather than a
 * children's-app or chatbot one.
 */
export function BuddySpeech({ children, className, tail = "left" }: BuddySpeechProps) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 10, scale: 0.98 }}
      animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: reduceMotion ? 0.15 : 0.35, ease: "easeOut" }}
      className={clsx(
        "relative rounded-2xl border border-buddy-border bg-buddy-surface px-5 py-4 shadow-[0_8px_24px_-8px_rgba(16,24,40,0.12)]",
        tail === "left" && "sm:ml-3",
        className
      )}
    >
      {tail === "left" && (
        <span
          aria-hidden="true"
          className="absolute -left-2 top-6 hidden h-4 w-4 rotate-45 border-b border-l border-buddy-border bg-buddy-surface sm:block"
        />
      )}
      {tail === "bottom" && (
        <span
          aria-hidden="true"
          className="absolute -bottom-2 left-8 h-4 w-4 rotate-45 border-b border-r border-buddy-border bg-buddy-surface"
        />
      )}
      <div className="text-[15px] leading-relaxed text-buddy-text-primary">{children}</div>
    </motion.div>
  );
}

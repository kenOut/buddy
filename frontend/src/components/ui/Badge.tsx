import type { HTMLAttributes } from "react";
import clsx from "clsx";

type Tone = "neutral" | "success" | "warning" | "info" | "coral";

const toneClasses: Record<Tone, string> = {
  neutral: "bg-buddy-border/60 text-buddy-muted",
  success: "bg-buddy-aurora/15 text-emerald-700 dark:text-emerald-400",
  warning: "bg-buddy-sunrise/25 text-amber-800 dark:text-amber-400",
  info: "bg-buddy-primary/10 text-buddy-primary-dark",
  coral: "bg-buddy-coral/15 text-red-600 dark:text-red-400",
};

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

export function Badge({ tone = "neutral", className, ...props }: BadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full px-3 py-1 text-xs font-medium capitalize",
        toneClasses[tone],
        className
      )}
      {...props}
    />
  );
}

import type { HTMLAttributes } from "react";
import clsx from "clsx";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={clsx(
        "rounded-2xl border border-buddy-border bg-buddy-surface p-6 shadow-sm",
        className
      )}
      {...props}
    />
  );
}

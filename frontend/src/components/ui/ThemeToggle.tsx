"use client";

import clsx from "clsx";

import { useTheme } from "@/lib/theme-context";

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, mounted, toggleTheme } = useTheme();
  const isDark = mounted && theme === "dark";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      title={isDark ? "Switch to light theme" : "Switch to dark theme"}
      className={clsx(
        "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-buddy-muted transition-colors hover:bg-buddy-border/40 hover:text-foreground",
        className,
      )}
    >
      {/* Rendered identically until mounted (both match the SSR default of
       * "light"), so there's nothing for hydration to disagree about. */}
      {isDark ? (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z"
          />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
          <circle cx="12" cy="12" r="4" />
          <path
            strokeLinecap="round"
            d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"
          />
        </svg>
      )}
    </button>
  );
}

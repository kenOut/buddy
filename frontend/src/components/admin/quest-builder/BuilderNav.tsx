"use client";

import clsx from "clsx";

export type BuilderSectionKey =
  | "basic-info"
  | "challenge"
  | "work-evidence"
  | "evaluation"
  | "capabilities"
  | "assign-publish";

const SECTIONS: { key: BuilderSectionKey; label: string }[] = [
  { key: "basic-info", label: "Basic Info" },
  { key: "challenge", label: "Challenge" },
  { key: "work-evidence", label: "Work & Evidence" },
  { key: "evaluation", label: "Evaluation" },
  { key: "capabilities", label: "Capabilities" },
  { key: "assign-publish", label: "Assign & Publish" },
];

export function BuilderNav({
  current,
  onChange,
}: {
  current: BuilderSectionKey;
  onChange: (section: BuilderSectionKey) => void;
}) {
  return (
    <nav
      aria-label="Quest Builder sections"
      className="-mx-1 flex gap-1 overflow-x-auto border-b border-buddy-border px-1 pb-0.5"
    >
      {SECTIONS.map((s) => (
        <button
          key={s.key}
          type="button"
          onClick={() => onChange(s.key)}
          aria-current={current === s.key ? "step" : undefined}
          className={clsx(
            "shrink-0 whitespace-nowrap rounded-t-lg border-b-2 px-4 py-2 text-sm font-medium transition-colors",
            current === s.key
              ? "border-buddy-primary text-buddy-primary"
              : "border-transparent text-buddy-muted hover:text-foreground"
          )}
        >
          {s.label}
        </button>
      ))}
    </nav>
  );
}

"use client";

import { Card } from "@/components/ui/Card";
import type { QuestQualityCheck, QuestQualityValidation } from "@/lib/types";
import type { BuilderSectionKey } from "./BuilderNav";

const SECTION_LABEL: Record<string, string> = {
  "basic-info": "Basic Info",
  challenge: "Challenge",
  "work-evidence": "Work & Evidence",
  evaluation: "Evaluation",
  capabilities: "Capabilities",
  "assign-publish": "Assign & Publish",
};

function isBuilderSection(section: string): section is BuilderSectionKey {
  return section in SECTION_LABEL;
}

/**
 * Phase 6B Stage 7 — the Quest Quality panel. Deliberately NOT a
 * numeric score: every row is a plain pass/fail/advisory statement, and
 * the only aggregate signal is the Publish button's disabled state. The
 * backend (quest_quality_service.py) is the sole source of truth for
 * what's satisfied — this component only renders what it returns and
 * offers a one-click jump to the section that needs attention.
 */
export function QuestQualityPanel({
  validation,
  onNavigateToSection,
}: {
  validation: QuestQualityValidation | null;
  onNavigateToSection: (section: BuilderSectionKey) => void;
}) {
  if (!validation) {
    return (
      <Card>
        <p className="text-sm text-buddy-muted">Checking Quest quality…</p>
      </Card>
    );
  }

  // One row per check, satisfied ones first read like a checklist,
  // unsatisfied ERRORs get a "Go to section" jump link — the checklist
  // itself already implies why publish is disabled without a score.
  const rows = validation.checks;

  return (
    <Card className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
        Quest Quality
      </p>
      <ul className="space-y-2">
        {rows.map((check) => (
          <QualityRow key={check.code} check={check} onNavigateToSection={onNavigateToSection} />
        ))}
      </ul>
      {validation.ready ? (
        <p className="text-sm text-emerald-700">
          Ready to publish — every required check has passed.
        </p>
      ) : (
        <p className="text-sm text-buddy-muted">
          Resolve the ✕ items above before publishing. ⚠ items are recommendations and
          don&rsquo;t block publishing.
        </p>
      )}
    </Card>
  );
}

function QualityRow({
  check,
  onNavigateToSection,
}: {
  check: QuestQualityCheck;
  onNavigateToSection: (section: BuilderSectionKey) => void;
}) {
  const icon = check.satisfied ? "✓" : check.severity === "ERROR" ? "✕" : "⚠";
  const iconColor = check.satisfied
    ? "text-emerald-600"
    : check.severity === "ERROR"
      ? "text-red-600"
      : "text-amber-600";
  const textColor = check.satisfied ? "text-foreground" : "text-buddy-text-secondary";

  return (
    <li>
      <div className="flex items-start gap-2 text-sm">
        <span className={iconColor} aria-hidden="true">
          {icon}
        </span>
        <span className={textColor}>{check.message}</span>
      </div>
      {!check.satisfied && isBuilderSection(check.section) && (
        <button
          type="button"
          onClick={() => onNavigateToSection(check.section as BuilderSectionKey)}
          className="ml-6 mt-0.5 text-xs font-medium text-buddy-primary hover:underline"
        >
          → Go to {SECTION_LABEL[check.section]}
        </button>
      )}
    </li>
  );
}

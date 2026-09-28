"use client";

import { useState } from "react";
import clsx from "clsx";

import type { QuestEvidenceItem, QuestEvidenceType } from "@/lib/types";

const EVIDENCE_TYPE_LABELS: Record<QuestEvidenceType, string> = {
  METRICS: "Metrics",
  LOGS: "Logs",
  SERVICES: "Services",
  TIMELINE: "Timeline",
  SCREENSHOT: "Screenshots",
  DOCUMENT: "Documents",
  CODE: "Code",
  DATASET: "Datasets",
  TEXT: "Notes",
  OTHER: "Other",
};

/**
 * Renders whatever evidence types are actually present on this quest —
 * tabs are generated from the distinct evidence_type values found, never
 * a hard-coded Metrics/Logs/Services/Timeline set (that's the existing
 * SRE Mission's shape, not Quest's — see Stage 4 spec §2/§10).
 *
 * `reviewedIds`/`onToggleReviewed` (Phase 7 Stage 3) are optional and
 * additive — GenericWorkspace's usage (no props passed) renders exactly
 * as before; only a Workspace that wants a "mark as reviewed" affordance
 * (currently just TroubleshootWorkspace's EvidenceExplorer) passes them.
 */
export function QuestEvidencePanel({
  evidence,
  reviewedIds,
  onToggleReviewed,
}: {
  evidence: QuestEvidenceItem[];
  reviewedIds?: Set<string>;
  onToggleReviewed?: (evidenceId: string) => void;
}) {
  const types = Array.from(new Set(evidence.map((e) => e.evidence_type)));
  const [active, setActive] = useState<QuestEvidenceType | undefined>(types[0]);

  if (evidence.length === 0) {
    return (
      <p className="text-sm text-buddy-muted">No evidence was attached to this quest.</p>
    );
  }

  const activeType = active ?? types[0];
  const activeItems = evidence
    .filter((e) => e.evidence_type === activeType)
    .slice()
    .sort((a, b) => a.sort_order - b.sort_order);

  return (
    <div>
      <div
        role="tablist"
        aria-label="Evidence sources"
        className="flex flex-wrap gap-1 border-b border-buddy-border"
      >
        {types.map((type) => (
          <button
            key={type}
            type="button"
            role="tab"
            aria-selected={activeType === type}
            onClick={() => setActive(type)}
            className={clsx(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-buddy-primary",
              activeType === type
                ? "border-buddy-primary text-buddy-primary"
                : "border-transparent text-buddy-muted hover:text-buddy-text-primary"
            )}
          >
            {EVIDENCE_TYPE_LABELS[type] ?? type}
          </button>
        ))}
      </div>

      <ul className="mt-4 space-y-3">
        {activeItems.map((item) => (
          <QuestEvidenceCard
            key={item.id}
            item={item}
            reviewed={reviewedIds?.has(item.id) ?? false}
            onToggleReviewed={onToggleReviewed ? () => onToggleReviewed(item.id) : undefined}
          />
        ))}
      </ul>
    </div>
  );
}

function QuestEvidenceCard({
  item,
  reviewed,
  onToggleReviewed,
}: {
  item: QuestEvidenceItem;
  reviewed?: boolean;
  onToggleReviewed?: () => void;
}) {
  const entries = Object.entries(item.content ?? {});
  const monospaceHint = item.evidence_type === "CODE" || item.evidence_type === "DATASET";

  return (
    <li className="rounded-lg bg-buddy-cloud px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <p className="font-medium text-buddy-text-primary">{item.title}</p>
        {onToggleReviewed && (
          <label className="flex shrink-0 cursor-pointer items-center gap-1.5 text-xs text-buddy-muted">
            <input
              type="checkbox"
              checked={reviewed ?? false}
              onChange={onToggleReviewed}
              aria-label={`Mark "${item.title}" as reviewed`}
              className="h-3.5 w-3.5 accent-[var(--buddy-primary)]"
            />
            Reviewed
          </label>
        )}
      </div>
      {item.description && (
        <p className="mt-1 text-sm text-buddy-text-secondary">{item.description}</p>
      )}
      {entries.length > 0 && (
        <dl className="mt-2 space-y-1.5">
          {entries.map(([key, value]) => {
            const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
            const multiline = monospaceHint || text.includes("\n");
            return (
              <div key={key}>
                <dt className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">
                  {key}
                </dt>
                {multiline ? (
                  <pre className="mt-1 overflow-x-auto rounded-md bg-buddy-navy/5 p-2 text-xs text-buddy-text-primary">
                    {text}
                  </pre>
                ) : (
                  <dd className="text-sm text-buddy-text-secondary">{text}</dd>
                )}
              </div>
            );
          })}
        </dl>
      )}
    </li>
  );
}

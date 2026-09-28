"use client";

import { useRef } from "react";
import clsx from "clsx";

import type { EvidenceItem, MissionScenario, TimelineItem } from "@/lib/types";

export type EvidenceCategory = "metrics" | "logs" | "services" | "timeline";

const TABS: { key: EvidenceCategory; label: string }[] = [
  { key: "metrics", label: "Metrics" },
  { key: "logs", label: "Logs" },
  { key: "services", label: "Services" },
  { key: "timeline", label: "Timeline" },
];

export function evidenceKeysFor(scenario: MissionScenario, category: EvidenceCategory): string[] {
  const items = category === "timeline" ? scenario.timeline : scenario[category];
  return items.map((item) => `${category}:${item.id}`);
}

interface EvidencePanelProps {
  scenario: MissionScenario;
  activeTab: EvidenceCategory;
  onOpenTab: (tab: EvidenceCategory) => void;
  viewedKeys: Set<string>;
}

export function EvidencePanel({ scenario, activeTab, onOpenTab, viewedKeys }: EvidencePanelProps) {
  const tabRefs = useRef<Record<EvidenceCategory, HTMLButtonElement | null>>({
    metrics: null,
    logs: null,
    services: null,
    timeline: null,
  });

  // WAI-ARIA tabs pattern: arrow keys move focus between tabs and activate
  // them immediately (automatic activation); Home/End jump to the ends.
  const handleKeyDown = (event: React.KeyboardEvent) => {
    const currentIndex = TABS.findIndex((t) => t.key === activeTab);
    let nextIndex: number | null = null;

    if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % TABS.length;
    else if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + TABS.length) % TABS.length;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = TABS.length - 1;

    if (nextIndex !== null) {
      event.preventDefault();
      const nextTab = TABS[nextIndex].key;
      onOpenTab(nextTab);
      tabRefs.current[nextTab]?.focus();
    }
  };

  return (
    <div>
      <div
        role="tablist"
        aria-label="Evidence sources"
        onKeyDown={handleKeyDown}
        className="flex flex-wrap gap-1 border-b border-buddy-border"
      >
        {TABS.map((tab) => {
          const keys = evidenceKeysFor(scenario, tab.key);
          const inspected = keys.length > 0 && keys.every((k) => viewedKeys.has(k));
          const selected = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              ref={(el) => {
                tabRefs.current[tab.key] = el;
              }}
              role="tab"
              type="button"
              aria-selected={selected}
              aria-controls={`evidence-panel-${tab.key}`}
              id={`evidence-tab-${tab.key}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => onOpenTab(tab.key)}
              className={clsx(
                "-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-buddy-primary",
                selected
                  ? "border-buddy-primary text-buddy-primary"
                  : "border-transparent text-buddy-muted hover:text-buddy-text-primary"
              )}
            >
              {tab.label}
              {inspected && (
                <span className="text-buddy-aurora" aria-hidden="true">
                  ✓
                </span>
              )}
            </button>
          );
        })}
      </div>

      {TABS.map((tab) => (
        <div
          key={tab.key}
          role="tabpanel"
          id={`evidence-panel-${tab.key}`}
          aria-labelledby={`evidence-tab-${tab.key}`}
          hidden={activeTab !== tab.key}
          className="pt-4"
        >
          {tab.key === "timeline" ? (
            <TimelineList items={scenario.timeline} />
          ) : (
            <EvidenceList items={scenario[tab.key]} />
          )}
        </div>
      ))}
    </div>
  );
}

function EvidenceList({ items }: { items: EvidenceItem[] }) {
  return (
    <ul className="space-y-2.5">
      {items.map((item) => (
        <li key={item.id} className="rounded-lg bg-buddy-cloud px-3 py-2 text-sm">
          <span className="font-medium text-buddy-text-primary">{item.label}:</span>{" "}
          <span className="text-buddy-text-secondary">{item.detail}</span>
        </li>
      ))}
    </ul>
  );
}

function TimelineList({ items }: { items: TimelineItem[] }) {
  return (
    <ul className="space-y-2.5">
      {items.map((item) => (
        <li key={item.id} className="flex gap-3 rounded-lg bg-buddy-cloud px-3 py-2 text-sm">
          <span className="shrink-0 font-mono text-xs text-buddy-muted">{item.time}</span>
          <span className="text-buddy-text-secondary">{item.label}</span>
        </li>
      ))}
    </ul>
  );
}

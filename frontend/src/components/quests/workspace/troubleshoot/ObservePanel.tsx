import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
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
 * "Observe" — a light orientation moment before the employee opens
 * anything, per the Stage 2 contract: presentational only, not a
 * tracked action. Shows evidence titles and types at a glance (never
 * full content — that stays inside EvidenceExplorer), derived entirely
 * from what the manager already authored.
 */
export function ObservePanel({ evidence }: { evidence: QuestEvidenceItem[] }) {
  if (evidence.length === 0) {
    return (
      <Card>
        <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
          What&rsquo;s available
        </p>
        <p className="mt-2 text-sm text-buddy-muted">No evidence was attached to this quest.</p>
      </Card>
    );
  }

  const sorted = evidence.slice().sort((a, b) => a.sort_order - b.sort_order);

  return (
    <Card>
      <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
        What&rsquo;s available before you dig in
      </p>
      <p className="mt-1 text-sm text-buddy-text-secondary">
        A quick look at what you have to work with — open each source below when you&rsquo;re ready to
        investigate.
      </p>
      <ul className="mt-3 space-y-1.5">
        {sorted.map((item) => (
          <li key={item.id} className="flex items-center gap-2 text-sm text-buddy-text-primary">
            <Badge tone="info">{EVIDENCE_TYPE_LABELS[item.evidence_type] ?? item.evidence_type}</Badge>
            {item.title}
          </li>
        ))}
      </ul>
    </Card>
  );
}

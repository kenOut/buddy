import { QuestEvidencePanel } from "@/components/quests/QuestEvidencePanel";
import type { QuestEvidenceItem } from "@/lib/types";

/**
 * A thin Troubleshoot-specific wrapper around the existing
 * QuestEvidencePanel — reuses all of its tab/content rendering
 * unmodified, adding only the "mark as reviewed" affordance via the
 * additive `reviewedIds`/`onToggleReviewed` props Stage 3 added to that
 * shared component. GenericWorkspace's own usage of QuestEvidencePanel
 * (no such props passed) is untouched.
 *
 * Marking is explicit (a checkbox the employee ticks), not inferred from
 * passive viewing — no hover/scroll/tab-switch tracking, per the Stage 2
 * contract's explicit instruction to avoid surveillance-level signals.
 */
export function EvidenceExplorer({
  evidence,
  reviewedIds,
  onToggleReviewed,
}: {
  evidence: QuestEvidenceItem[];
  reviewedIds: Set<string>;
  onToggleReviewed: (evidenceId: string) => void;
}) {
  return <QuestEvidencePanel evidence={evidence} reviewedIds={reviewedIds} onToggleReviewed={onToggleReviewed} />;
}

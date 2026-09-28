"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { getQuestDetailAnalytics } from "@/lib/analytics";
import type { QuestAnalyticsSignal, QuestAnalyticsSummary, QuestDetailAnalytics } from "@/lib/types";

/** Neutral, descriptive labels — "Signals"/"Patterns," never a verdict
 * like "bad Quest" (Phase 6E Part 7). Tone reflects whether it's
 * something to look at (warning) or a plain positive pattern (info). */
const SIGNAL_LABEL: Record<QuestAnalyticsSignal, string> = {
  ZERO_ATTEMPTS: "No attempts yet",
  SUBMITTED_NOT_COMPLETED: "Submitted work not yet completed",
  NO_EVIDENCE_GENERATED: "Completed without capability evidence",
  NEVER_RECOMMENDED: "Never recommended",
  FREQUENTLY_RECOMMENDED: "Frequently recommended",
  HIGH_COMPLETION_ACTIVITY: "High completion activity",
};

const SIGNAL_TONE: Record<QuestAnalyticsSignal, "warning" | "info" | "success"> = {
  ZERO_ATTEMPTS: "warning",
  SUBMITTED_NOT_COMPLETED: "warning",
  NO_EVIDENCE_GENERATED: "warning",
  NEVER_RECOMMENDED: "warning",
  FREQUENTLY_RECOMMENDED: "info",
  HIGH_COMPLETION_ACTIVITY: "success",
};

export function QuestActivityTable({
  quests,
  departmentId,
}: {
  quests: QuestAnalyticsSummary[];
  departmentId: string | null;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (quests.length === 0) {
    return (
      <Card>
        <p className="text-sm text-buddy-muted">No Quest activity yet.</p>
      </Card>
    );
  }

  return (
    <Card className="p-0">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="border-b border-buddy-border text-xs uppercase tracking-wide text-buddy-muted">
            <tr>
              <th className="px-6 py-3">Quest</th>
              <th className="px-6 py-3">Type</th>
              <th className="px-6 py-3">Status</th>
              <th className="px-6 py-3">Assigned</th>
              <th className="px-6 py-3">Attempts</th>
              <th className="px-6 py-3">Completed</th>
              <th className="px-6 py-3">Signals</th>
            </tr>
          </thead>
          <tbody>
            {quests.map((quest) => (
              <QuestRow
                key={quest.quest_id}
                quest={quest}
                departmentId={departmentId}
                expanded={expandedId === quest.quest_id}
                onToggle={() => setExpandedId(expandedId === quest.quest_id ? null : quest.quest_id)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function QuestRow({
  quest,
  departmentId,
  expanded,
  onToggle,
}: {
  quest: QuestAnalyticsSummary;
  departmentId: string | null;
  expanded: boolean;
  onToggle: () => void;
}) {
  const [detail, setDetail] = useState<QuestDetailAnalytics | null>(null);
  const [loading, setLoading] = useState(false);

  const handleToggle = () => {
    onToggle();
    if (!detail && !expanded) {
      setLoading(true);
      getQuestDetailAnalytics(quest.quest_id, departmentId)
        .then(setDetail)
        .finally(() => setLoading(false));
    }
  };

  return (
    <>
      <tr className="border-b border-buddy-border last:border-0">
        <td className="px-6 py-3">
          <button
            type="button"
            onClick={handleToggle}
            className="font-medium text-foreground hover:text-buddy-primary"
            aria-expanded={expanded}
          >
            {quest.title}
          </button>
        </td>
        <td className="px-6 py-3">
          <Badge tone="info">{quest.quest_type}</Badge>
        </td>
        <td className="px-6 py-3 text-buddy-muted">{quest.status}</td>
        <td className="px-6 py-3 text-buddy-muted">{quest.assigned_employees}</td>
        <td className="px-6 py-3 text-buddy-muted">{quest.attempts_total}</td>
        <td className="px-6 py-3 text-buddy-muted">
          {quest.attempts_completed}
          {quest.completion_rate !== null && (
            <span className="ml-1 text-xs">({Math.round(quest.completion_rate * 100)}%)</span>
          )}
        </td>
        <td className="px-6 py-3">
          <div className="flex flex-wrap gap-1">
            {quest.signals.length === 0 ? (
              <span className="text-xs text-buddy-muted">—</span>
            ) : (
              quest.signals.map((signal) => (
                <Badge key={signal} tone={SIGNAL_TONE[signal]}>
                  {SIGNAL_LABEL[signal]}
                </Badge>
              ))
            )}
          </div>
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-buddy-border bg-buddy-cloud/40 last:border-0">
          <td colSpan={7} className="px-6 py-4">
            {loading && <p className="text-sm text-buddy-muted">Loading Quest detail…</p>}
            {!loading && detail && <QuestDetailPanel detail={detail} />}
          </td>
        </tr>
      )}
    </>
  );
}

function QuestDetailPanel({ detail }: { detail: QuestDetailAnalytics }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">
          Attempt breakdown
        </p>
        <ul className="mt-2 space-y-1 text-sm text-buddy-text-secondary">
          <li>Not started: {detail.attempts_not_started}</li>
          <li>In progress: {detail.attempts_in_progress}</li>
          <li>Submitted: {detail.attempts_submitted}</li>
          <li>Evaluating: {detail.attempts_evaluating}</li>
          <li>Completed: {detail.attempts_completed}</li>
        </ul>
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">
          Capability evidence produced
        </p>
        {detail.capability_breakdown.length === 0 ? (
          <p className="mt-2 text-sm text-buddy-muted">
            Capability evidence will appear after employees complete evaluated work.
          </p>
        ) : (
          <ul className="mt-2 space-y-1 text-sm text-buddy-text-secondary">
            {detail.capability_breakdown.map((c) => (
              <li key={c.capability_key}>
                {c.capability_name}: {c.evidence_count}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-xs text-buddy-muted">
          Recommended {detail.recommendation_count} time{detail.recommendation_count === 1 ? "" : "s"} ·{" "}
          {detail.evaluation_criteria_count} evaluation criterion/criteria defined
        </p>
      </div>
    </div>
  );
}

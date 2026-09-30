"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { getEmployeePerformance } from "@/lib/managerPerformance";
import type {
  CapabilityLevel,
  ManagerCapabilitySummary,
  ManagerEmployeePerformanceResponse,
  ManagerMissionPerformance,
  ManagerQuestPerformance,
  ReadinessBlocker,
  ThresholdStatus,
} from "@/lib/types";

const capabilityLevelTone: Record<CapabilityLevel, "neutral" | "warning" | "info" | "success"> = {
  NOT_OBSERVED: "neutral",
  DEVELOPING: "warning",
  CAPABLE: "info",
  STRONG: "success",
};

const thresholdTone: Record<ThresholdStatus, "success" | "coral" | "neutral"> = {
  SATISFIED: "success",
  BELOW_THRESHOLD: "coral",
  INCOMPLETE: "neutral",
};

const thresholdLabel: Record<ThresholdStatus, string> = {
  SATISFIED: "Meets minimum",
  BELOW_THRESHOLD: "Below minimum",
  INCOMPLETE: "Incomplete",
};

function formatScore(score: number | null): string {
  return score === null ? "—" : `${Math.round(score)}%`;
}

function statusTone(status: string | null): "neutral" | "info" | "success" | "warning" {
  if (status === null) return "neutral";
  const normalized = status.toLowerCase();
  if (normalized === "completed") return "success";
  if (normalized === "submitted" || normalized === "evaluating") return "warning";
  if (normalized === "in_progress") return "info";
  return "neutral";
}

/** Stage 2 — `threshold_status` (when present, i.e. the item is
 * required) is the authoritative color signal, since it's the one that
 * actually determines readiness; `passed` alone (the item's own
 * internal grading result) is a weaker, fallback signal for optional
 * items that have no threshold to be measured against. */
function scoreTone(item: { passed: boolean | null; threshold_status: ThresholdStatus | null }): string {
  if (item.threshold_status === "BELOW_THRESHOLD") return "text-buddy-coral";
  if (item.threshold_status === null && item.passed === false) return "text-buddy-coral";
  return "text-buddy-muted";
}

function MissionRow({ mission }: { mission: ManagerMissionPerformance }) {
  return (
    <tr className="border-b border-buddy-border last:border-0">
      <td className="px-4 py-2.5">
        <span className="text-sm text-foreground">{mission.title}</span>
        {mission.required && (
          <Badge tone="coral" className="ml-2">
            Required
          </Badge>
        )}
      </td>
      <td className="px-4 py-2.5">
        <Badge tone={statusTone(mission.attempt_status ?? mission.assignment_status)}>
          {(mission.attempt_status ?? mission.assignment_status).replace("_", " ")}
        </Badge>
      </td>
      <td className="px-4 py-2.5 text-right text-sm tabular-nums">
        <span className={scoreTone(mission)}>{formatScore(mission.score)}</span>
      </td>
      <td className="px-4 py-2.5 text-right text-sm tabular-nums text-buddy-muted">
        {mission.minimum_score === null ? "—" : `${Math.round(mission.minimum_score)}%`}
      </td>
      <td className="px-4 py-2.5">
        {mission.threshold_status && (
          <Badge tone={thresholdTone[mission.threshold_status]}>
            {thresholdLabel[mission.threshold_status]}
          </Badge>
        )}
      </td>
    </tr>
  );
}

function QuestRow({ quest }: { quest: ManagerQuestPerformance }) {
  return (
    <tr className="border-b border-buddy-border last:border-0">
      <td className="px-4 py-2.5">
        <span className="text-sm text-foreground">{quest.title}</span>
        {quest.required && (
          <Badge tone="coral" className="ml-2">
            Required
          </Badge>
        )}
      </td>
      <td className="px-4 py-2.5">
        <Badge tone={statusTone(quest.attempt_status)}>
          {(quest.attempt_status ?? "not started").toLowerCase().replace("_", " ")}
        </Badge>
      </td>
      <td className="px-4 py-2.5 text-right text-sm tabular-nums">
        <span className={scoreTone(quest)}>{formatScore(quest.score)}</span>
      </td>
      <td className="px-4 py-2.5 text-right text-sm tabular-nums text-buddy-muted">
        {quest.minimum_score === null ? "—" : `${Math.round(quest.minimum_score)}%`}
      </td>
      <td className="px-4 py-2.5">
        {quest.threshold_status && (
          <Badge tone={thresholdTone[quest.threshold_status]}>{thresholdLabel[quest.threshold_status]}</Badge>
        )}
      </td>
    </tr>
  );
}

function BlockerRow({ blocker }: { blocker: ReadinessBlocker }) {
  if (blocker.type === "ONBOARDING_INCOMPLETE") {
    return (
      <li className="rounded-lg border border-buddy-border px-4 py-3">
        <p className="text-sm font-medium text-foreground">Onboarding</p>
        <p className="text-xs text-buddy-muted">Not yet completed.</p>
      </li>
    );
  }

  const isBelowThreshold =
    blocker.type === "REQUIRED_MISSION_BELOW_THRESHOLD" || blocker.type === "REQUIRED_QUEST_BELOW_THRESHOLD";

  return (
    <li className="rounded-lg border border-buddy-border px-4 py-3">
      <p className="text-sm font-medium text-foreground">{blocker.title}</p>
      {isBelowThreshold ? (
        <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-buddy-muted">
          <span className="text-buddy-coral">Below required performance</span>
          <span>
            Score <span className="font-medium text-foreground">{formatScore(blocker.score)}</span>
          </span>
          <span>
            Required{" "}
            <span className="font-medium text-foreground">{formatScore(blocker.minimum_score)}</span>
          </span>
          {blocker.score !== null && blocker.minimum_score !== null && (
            <span>
              Gap{" "}
              <span className="font-medium text-foreground">
                {Math.round(blocker.minimum_score - blocker.score)} pt
                {Math.round(blocker.minimum_score - blocker.score) === 1 ? "" : "s"}
              </span>
            </span>
          )}
        </div>
      ) : (
        <p className="mt-1 text-xs text-buddy-muted">
          <span className="text-buddy-coral">Not completed</span> &middot; Required: Yes
        </p>
      )}
    </li>
  );
}

function CapabilityRow({ capability }: { capability: ManagerCapabilitySummary }) {
  return (
    <div className="flex items-center justify-between border-b border-buddy-border py-2 last:border-0">
      <div>
        <p className="text-sm text-foreground">{capability.capability_name}</p>
        <p className="text-xs text-buddy-muted">
          {capability.evidence_count} {capability.evidence_count === 1 ? "observation" : "observations"}
        </p>
      </div>
      <Badge tone={capabilityLevelTone[capability.level]}>{capability.level.toLowerCase().replace("_", " ")}</Badge>
    </div>
  );
}

/**
 * Manager Performance & Readiness Visibility — Stage 1. Everything
 * rendered here comes straight from GET /employees/{id}/performance
 * (manager_performance_service.py) — completion, performance (score),
 * capability level, and readiness are kept visually distinct on
 * purpose (see that service's own module docstring): this component
 * never blends them into one number, and `average_score` is shown only
 * as an informational summary, never as a stand-in for `ready`.
 */
export function ManagerPerformanceSection({ employeeId }: { employeeId: string }) {
  const [data, setData] = useState<ManagerEmployeePerformanceResponse | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  // Adjust state when employeeId changes (React's documented pattern for
  // this — see https://react.dev/learn/you-might-not-need-an-effect),
  // rather than resetting loading/error synchronously inside the effect
  // below: this component is mounted once per employee detail page, so
  // `loading`'s own initial value already covers the mount case, and
  // this only ever fires again if `employeeId` itself changes under an
  // already-mounted instance.
  const [prevEmployeeId, setPrevEmployeeId] = useState(employeeId);
  if (employeeId !== prevEmployeeId) {
    setPrevEmployeeId(employeeId);
    setLoading(true);
    setError(false);
  }

  useEffect(() => {
    let cancelled = false;
    getEmployeePerformance(employeeId)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [employeeId]);

  if (error) {
    return (
      <Card>
        <p className="text-sm text-buddy-coral">
          Couldn&rsquo;t load readiness &amp; performance data. Try refreshing the page.
        </p>
      </Card>
    );
  }

  if (loading || !data) {
    return (
      <Card>
        <p className="text-sm text-buddy-muted">Loading readiness &amp; performance…</p>
      </Card>
    );
  }

  const { readiness, missions, quests, capabilities, performance_summary } = data;
  const requiredTotal =
    readiness.required_quest_count + readiness.required_mission_count;
  const requiredComplete =
    readiness.completed_required_quest_count + readiness.completed_required_mission_count;

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">
            Readiness &amp; Performance
          </p>
          <Badge tone={readiness.ready ? "success" : "coral"} className="text-sm">
            {readiness.ready ? "Ready" : "Not ready"}
          </Badge>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <p className="text-xs text-buddy-muted">Onboarding</p>
            <p className="text-sm font-medium text-foreground">
              {readiness.onboarding_completed ? "✓ Complete" : "Not complete"}
            </p>
          </div>
          <div>
            <p className="text-xs text-buddy-muted">Required work</p>
            <p className="text-sm font-medium text-foreground">
              {requiredTotal === 0 ? "None assigned" : `${requiredComplete} / ${requiredTotal} complete`}
            </p>
            {readiness.required_items_below_threshold > 0 && (
              <p className="text-xs text-buddy-coral">
                {readiness.required_items_below_threshold} below minimum score
              </p>
            )}
          </div>
          <div>
            <p className="text-xs text-buddy-muted">Performance</p>
            <p className="text-sm font-medium text-foreground">
              {performance_summary.scored_items === 0
                ? "No scored work yet"
                : `${performance_summary.scored_items} scored item${performance_summary.scored_items === 1 ? "" : "s"} · avg ${formatScore(performance_summary.average_score)}`}
            </p>
          </div>
        </div>
      </Card>

      <Card>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-buddy-muted">
          Mission performance
        </p>
        {missions.length === 0 ? (
          <p className="text-sm text-buddy-muted">No missions assigned.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[480px] text-left">
              <thead className="border-b border-buddy-border text-xs uppercase tracking-wide text-buddy-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">Mission</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 text-right font-medium">Score</th>
                  <th className="px-4 py-2 text-right font-medium">Minimum</th>
                  <th className="px-4 py-2 font-medium">Meets bar?</th>
                </tr>
              </thead>
              <tbody>
                {missions.map((m) => (
                  <MissionRow key={m.id} mission={m} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-buddy-muted">
          Quest performance
        </p>
        {quests.length === 0 ? (
          <p className="text-sm text-buddy-muted">No quests assigned.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[480px] text-left">
              <thead className="border-b border-buddy-border text-xs uppercase tracking-wide text-buddy-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">Quest</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 text-right font-medium">Score</th>
                  <th className="px-4 py-2 text-right font-medium">Minimum</th>
                  <th className="px-4 py-2 font-medium">Meets bar?</th>
                </tr>
              </thead>
              <tbody>
                {quests.map((q) => (
                  <QuestRow key={q.id} quest={q} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-buddy-muted">
          Capabilities
        </p>
        {capabilities.length === 0 ? (
          <p className="text-sm text-buddy-muted">No capability evidence yet.</p>
        ) : (
          <div>
            {capabilities.map((c) => (
              <CapabilityRow key={c.capability_id} capability={c} />
            ))}
          </div>
        )}
      </Card>

      <Card>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-buddy-muted">
          Current blockers
        </p>
        {readiness.blockers.length === 0 ? (
          <p className="text-sm text-buddy-primary-dark">✓ No current readiness blockers</p>
        ) : (
          <ul className="space-y-2">
            {readiness.blockers.map((blocker, i) => (
              <BlockerRow key={blocker.item_id ?? `onboarding-${i}`} blocker={blocker} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

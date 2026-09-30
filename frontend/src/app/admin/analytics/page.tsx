"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import {
  getAnalyticsOverview,
  getCapabilityAnalytics,
  getDevelopmentSignals,
  getQuestAnalytics,
} from "@/lib/analytics";
import { api } from "@/lib/api";
import type {
  AnalyticsCapabilitiesResponse,
  AnalyticsDevelopmentSignalsResponse,
  AnalyticsOverview,
  AnalyticsQuestsResponse,
  Department,
} from "@/lib/types";
import { CapabilityDevelopmentSection } from "@/components/analytics/CapabilityDevelopmentSection";
import { DevelopmentSignalsSection } from "@/components/analytics/DevelopmentSignalsSection";
import { OverviewCards } from "@/components/analytics/OverviewCards";
import { QuestActivityFunnel } from "@/components/analytics/QuestActivityFunnel";
import { QuestActivityTable } from "@/components/analytics/QuestActivityTable";
import { RecentRecommendationsSection } from "@/components/analytics/RecentRecommendationsSection";

type LoadState =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | {
      phase: "ready";
      overview: AnalyticsOverview;
      quests: AnalyticsQuestsResponse;
      capabilities: AnalyticsCapabilitiesResponse;
      signals: AnalyticsDevelopmentSignalsResponse;
    };

export default function AnalyticsPage() {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [departmentId, setDepartmentId] = useState<string>("");
  const [state, setState] = useState<LoadState>({ phase: "loading" });
  const [retryTick, setRetryTick] = useState(0);

  useEffect(() => {
    api.get<Department[]>("/departments").then(setDepartments);
  }, []);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState({ phase: "loading" });
    const filter = departmentId || undefined;

    Promise.all([
      getAnalyticsOverview(filter),
      getQuestAnalytics(filter),
      getCapabilityAnalytics(filter),
      getDevelopmentSignals(filter),
    ])
      .then(([overview, quests, capabilities, signals]) => {
        if (cancelled) return;
        setState({ phase: "ready", overview, quests, capabilities, signals });
      })
      .catch(() => {
        if (!cancelled) {
          setState({ phase: "error", message: "Couldn't load analytics. Please try again." });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [departmentId, retryTick]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Manager Intelligence</h1>
          <p className="mt-1 text-sm text-buddy-muted">
            See what real work is revealing across your team.
          </p>
        </div>
        <select
          value={departmentId}
          onChange={(e) => setDepartmentId(e.target.value)}
          className="rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
          aria-label="Filter by department"
        >
          <option value="">All departments</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </div>

      {state.phase === "loading" && <p className="text-sm text-buddy-muted">Loading analytics…</p>}

      {state.phase === "error" && (
        <Card>
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {state.message}
          </p>
          <Button className="mt-3" onClick={() => setRetryTick((n) => n + 1)}>
            Try again
          </Button>
        </Card>
      )}

      {state.phase === "ready" && (
        <>
          <OverviewCards overview={state.overview} />

          <section className="space-y-4">
            <h2 className="text-lg font-semibold text-buddy-navy">Quest Activity</h2>
            <QuestActivityFunnel overview={state.overview} />
            <QuestActivityTable quests={state.quests.quests} departmentId={departmentId || null} />
          </section>

          <section className="space-y-4">
            <h2 className="text-lg font-semibold text-buddy-navy">Capability Development</h2>
            <CapabilityDevelopmentSection
              capabilities={state.capabilities.capabilities}
              departmentId={departmentId || null}
            />
          </section>

          <section className="space-y-4">
            <h2 className="text-lg font-semibold text-buddy-navy">Development Signals</h2>
            <DevelopmentSignalsSection
              signals={state.signals.development_areas}
              departmentId={departmentId || null}
            />
          </section>

          <section className="space-y-4">
            <h2 className="text-lg font-semibold text-buddy-navy">Recent Recommendations</h2>
            <RecentRecommendationsSection recommendations={state.overview.recent_recommendations} />
          </section>
        </>
      )}
    </div>
  );
}

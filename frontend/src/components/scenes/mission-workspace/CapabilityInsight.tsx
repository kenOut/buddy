"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import type { BuddyState } from "@/components/buddy/buddyStates";
import { BuddySpeech } from "@/components/buddy/BuddySpeech";
import { FadeIn } from "@/components/animations/FadeIn";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { evaluateMissionAttempt, getNextMission } from "@/lib/capabilities";
import type { CapabilityLevel, NextMissionResponse } from "@/lib/types";

type InsightState =
  | { phase: "evaluating" }
  | { phase: "failed" }
  | { phase: "ready"; result: Awaited<ReturnType<typeof evaluateMissionAttempt>> };

const LEVEL_COPY: Record<CapabilityLevel, string> = {
  NOT_OBSERVED: "not yet observed",
  DEVELOPING: "building",
  CAPABLE: "getting stronger at",
  STRONG: "showing real strength in",
};

const LEVEL_TONE: Record<CapabilityLevel, "neutral" | "info" | "success"> = {
  NOT_OBSERVED: "neutral",
  DEVELOPING: "neutral",
  CAPABLE: "info",
  STRONG: "success",
};

/**
 * The Phase 3A "Mission Complete -> What Buddy Observed -> Capability
 * Insight -> Next Mission" flow. Only rendered after a genuinely passed
 * submission (see InvestigationWorkspace) — this is capability feedback,
 * not a grading report, so it stays lightweight: a short observation, a
 * couple of capability words (never a raw score), and a next step.
 */
export function CapabilityInsight({
  attemptId,
  employeeId,
}: {
  attemptId: string;
  employeeId: string;
}) {
  const [state, setState] = useState<InsightState>({ phase: "evaluating" });
  const [nextMission, setNextMission] = useState<NextMissionResponse | null>(null);
  // Bumping this re-runs the effect below to retry after a failure —
  // same pattern as MissionWorkspace's retryTick.
  const [retryTick, setRetryTick] = useState(0);

  useEffect(() => {
    // No dedupe-by-ref guard here: React Strict Mode's dev-only
    // mount->cleanup->mount would mark the first mount's request
    // `cancelled` and a ref guard would then block the second (real)
    // mount from ever issuing its own request, leaving the UI stuck in
    // "evaluating" forever. Evaluation is idempotent server-side
    // (ai_evaluation_service.evaluate_attempt), so letting both real
    // invocations fire is safe — same pattern as MissionWorkspace's load
    // effect.
    let cancelled = false;
    evaluateMissionAttempt(attemptId, employeeId)
      .then((result) => {
        if (cancelled) return;
        setState({ phase: "ready", result });
        return getNextMission(employeeId).then((next) => {
          if (!cancelled) setNextMission(next);
        });
      })
      .catch(() => {
        if (!cancelled) setState({ phase: "failed" });
      });

    return () => {
      cancelled = true;
    };
  }, [attemptId, employeeId, retryTick]);

  const retry = () => {
    setState({ phase: "evaluating" });
    setRetryTick((n) => n + 1);
  };

  return (
    <div className="flex flex-col gap-4">
      {state.phase === "evaluating" && <ObservingBuddy />}

      {state.phase === "failed" && (
        <Card>
          <div className="flex items-start gap-3">
            <div className="h-10 w-10 shrink-0">
              <BuddyIllustration state="thinking" />
            </div>
            <div className="flex-1">
              <p className="text-sm text-buddy-text-secondary">
                Buddy is still analyzing your investigation. Try again in a moment.
              </p>
              <Button className="mt-3" onClick={retry}>
                Try again
              </Button>
            </div>
          </div>
        </Card>
      )}

      {state.phase === "ready" && (
        <>
          <ObservationCard summary={state.result.structured_result.summary} />
          <CapabilityCard capabilities={state.result.structured_result.capabilities} />
          {nextMission && <NextMissionCard response={nextMission} />}
        </>
      )}
    </div>
  );
}

function ObservingBuddy() {
  return (
    <FadeIn duration={0.4} className="flex items-start gap-3">
      <div className="h-10 w-10 shrink-0">
        <BuddyIllustration state="focused" />
      </div>
      <BuddySpeech className="flex-1 py-2.5">
        <p className="text-sm text-buddy-text-secondary">
          Give me a second — I&rsquo;m looking at what this investigation shows about how you work.
        </p>
      </BuddySpeech>
    </FadeIn>
  );
}

function ObservationCard({ summary }: { summary: string }) {
  return (
    <FadeIn duration={0.4}>
      <Card>
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 shrink-0">
            <BuddyIllustration state="curious" />
          </div>
          <div className="flex-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
              What Buddy observed
            </p>
            <p className="mt-2 text-sm text-buddy-text-primary">{summary}</p>
          </div>
        </div>
      </Card>
    </FadeIn>
  );
}

function CapabilityCard({
  capabilities,
}: {
  capabilities: { capability: string; level: CapabilityLevel }[];
}) {
  if (capabilities.length === 0) return null;

  return (
    <FadeIn duration={0.4} delay={0.1}>
      <Card>
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 shrink-0">
            <BuddyIllustration state="encouraging" />
          </div>
          <div className="flex-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
              Capability insight
            </p>
            <ul className="mt-2 flex flex-col gap-2">
              {capabilities.map((c) => (
                <li key={c.capability} className="flex items-center gap-2 text-sm text-buddy-text-primary">
                  <Badge tone={LEVEL_TONE[c.level]}>{c.level.replace("_", " ").toLowerCase()}</Badge>
                  <span>
                    You&rsquo;re {LEVEL_COPY[c.level]} {c.capability.replace(/_/g, " ")}.
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Card>
    </FadeIn>
  );
}

function NextMissionCard({ response }: { response: NextMissionResponse }) {
  const state: BuddyState = "guide";

  return (
    <FadeIn duration={0.4} delay={0.2}>
      <Card>
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 shrink-0">
            <BuddyIllustration state={state} />
          </div>
          <div className="flex-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
              Next up
            </p>
            <p className="mt-2 text-sm text-buddy-text-primary">{response.reason}</p>
            {response.mission && (
              <Link
                href={`/onboarding/missions/${response.mission.id}`}
                className="mt-3 inline-flex items-center justify-center rounded-full bg-buddy-primary px-5 py-2.5 text-sm font-medium text-white shadow-lg shadow-buddy-primary/25 hover:bg-buddy-primary-dark"
              >
                Go to &ldquo;{response.mission.title}&rdquo;
              </Link>
            )}
          </div>
        </div>
      </Card>
    </FadeIn>
  );
}

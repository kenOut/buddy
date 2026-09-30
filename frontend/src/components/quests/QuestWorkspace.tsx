"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ApiError } from "@/lib/api";
import { getNextQuest, getReadinessSummary } from "@/lib/capabilities";
import { createQuestAttempt, evaluateQuestAttempt, getEmployeeQuest, getQuestEligibility } from "@/lib/quests";
import { useOnboarding } from "@/lib/onboarding-context";
import type {
  EmployeeQuest,
  EmployeeReadinessSummary,
  NextQuestResponse,
  QuestAttempt,
  QuestEvaluationResult,
} from "@/lib/types";
import { QuestBuddy } from "./QuestBuddy";
import { QuestCapabilityInsight } from "./QuestCapabilityInsight";
import { QuestCompletion } from "./QuestCompletion";
import { QuestNextRecommendation } from "./QuestNextRecommendation";
import { QuestReadyTransition } from "./QuestReadyTransition";
import { resolveWorkspace } from "./workspace/resolveWorkspace";
import { useWorkspaceEngine } from "./workspace/useWorkspaceEngine";

type LoadState =
  | { phase: "loading" }
  | { phase: "not-eligible"; reason: "draft" | "archived" | "unassigned" }
  | { phase: "error"; message: string }
  | { phase: "ready"; quest: EmployeeQuest; attempt: QuestAttempt };

const NOT_ELIGIBLE_MESSAGE: Record<"draft" | "archived" | "unassigned", string> = {
  draft: "This Quest hasn't been published yet.",
  archived: "This Quest is no longer accepting new work.",
  unassigned: "This Quest isn't available to you.",
};

export function QuestWorkspace({ questId }: { questId: string }) {
  const { bundle } = useOnboarding();
  const [state, setState] = useState<LoadState>({ phase: "loading" });
  const [retryTick, setRetryTick] = useState(0);

  useEffect(() => {
    if (!bundle) return;
    const employeeId = bundle.employee.id;
    let cancelled = false;
    // Resets state when `questId` changes so stale data from a previous
    // quest can't flash while the new one loads — synchronous early
    // reset, nothing async to defer this into.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState({ phase: "loading" });

    getQuestEligibility(questId, employeeId)
      .then((eligibility) => {
        if (cancelled) return;
        if (!eligibility.eligible) {
          const reason: "draft" | "archived" | "unassigned" =
            eligibility.quest_status === "DRAFT"
              ? "draft"
              : eligibility.quest_status === "ARCHIVED"
                ? "archived"
                : "unassigned";
          setState({ phase: "not-eligible", reason });
          return;
        }
        return getEmployeeQuest(questId, employeeId).then((quest) =>
          createQuestAttempt(questId, employeeId).then((attempt) => {
            if (cancelled) return;
            setState({ phase: "ready", quest, attempt });
          })
        );
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setState({ phase: "error", message: "This quest couldn't be found." });
        } else {
          setState({ phase: "error", message: "Couldn't load this quest. Please try again." });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [bundle, questId, retryTick]);

  if (!bundle) return null;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 py-4">
      <Link
        href="/onboarding/missions"
        className="text-sm text-buddy-muted hover:text-buddy-text-primary"
      >
        ← Back to missions
      </Link>

      {state.phase === "loading" && (
        <div className="flex flex-col items-center gap-3 py-16 text-center">
          <div className="h-16 w-16">
            <BuddyIllustration state="thinking" />
          </div>
          <p className="text-sm text-buddy-muted">Buddy is pulling up your quest…</p>
        </div>
      )}

      {state.phase === "not-eligible" && (
        <Card>
          <div className="flex items-start gap-3">
            <div className="h-10 w-10 shrink-0">
              <BuddyIllustration state="curious" />
            </div>
            <p className="text-sm text-buddy-text-secondary">
              {NOT_ELIGIBLE_MESSAGE[state.reason]}
            </p>
          </div>
        </Card>
      )}

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
          {/* Phase 8H-4/8H-3: workspace-type-agnostic by construction —
              added once here, at the dispatcher level, never inside a
              per-workspace-type component. Shows explicitly for both
              states (not just "required") so its absence never reads as
              a bug — see QuestNextRecommendation for the same pattern. */}
          <div>
            <Badge tone={state.quest.required_for_readiness ? "info" : "neutral"}>
              {state.quest.required_for_readiness ? "Required for readiness" : "Optional"}
            </Badge>
          </div>
          <QuestWorkspaceContent
            key={state.attempt.id}
            quest={state.quest}
            attempt={state.attempt}
            employeeId={bundle.employee.id}
          />
        </>
      )}
    </div>
  );
}

/**
 * Phase 7 Stage 1 — this component is now the top of the Workspace
 * Engine, not the workspace itself. It owns nothing about how a Quest's
 * work gets rendered (that's resolveWorkspace's job) or how the attempt
 * is loaded/saved/submitted (that's useWorkspaceEngine's job); it only
 * decides, from the attempt's status, whether an in-progress Workspace
 * or the post-submission evaluation flow should be on screen — exactly
 * the same branch this component made before the extraction.
 */
function QuestWorkspaceContent({
  quest,
  attempt: initialAttempt,
  employeeId,
}: {
  quest: EmployeeQuest;
  attempt: QuestAttempt;
  employeeId: string;
}) {
  const engine = useWorkspaceEngine({ quest, attempt: initialAttempt, employeeId });

  const isFinalized =
    engine.attempt.status === "SUBMITTED" ||
    engine.attempt.status === "EVALUATING" ||
    engine.attempt.status === "COMPLETED";

  if (isFinalized) {
    return <QuestEvaluationFlow attemptId={engine.attempt.id} employeeId={employeeId} />;
  }

  const { component: Workspace } = resolveWorkspace(quest.workspace_type);

  return (
    <Workspace
      context={{ quest, attempt: engine.attempt, employeeId }}
      lifecycle={engine.lifecycle}
      draft={engine.draft}
      saveState={engine.saveState}
      submitError={engine.submitError}
      canSubmit={engine.canSubmit}
      requiredTasks={engine.requiredTasks}
      onFieldChange={engine.onFieldChange}
      onWorkspacePayloadChange={engine.onWorkspacePayloadChange}
      onCompleteTask={engine.onCompleteTask}
      onRetrySave={engine.onRetrySave}
      onSubmit={engine.onSubmit}
    />
  );
}

type EvaluationState =
  | { phase: "evaluating" }
  | { phase: "failed" }
  | { phase: "ready"; result: QuestEvaluationResult | null; readiness: EmployeeReadinessSummary | null };

/**
 * Everything from SUBMITTED onward: triggers evaluation (idempotent —
 * safe to call whether this is the very first evaluation or a page
 * revisit of an already-COMPLETED attempt, same as Phase 3A's
 * CapabilityInsight.tsx does for missions), shows "Buddy is reviewing
 * your work" while it runs, then the capability insight and completion
 * screen. `result` can be null (a quest with no capability mappings
 * completes deterministically with nothing to interpret) — the
 * completion screen alone still communicates that the work was received.
 *
 * Phase 8H-5: readiness is fetched (GET /employees/{id}/readiness-summary,
 * Phase 8H-1 — the same authoritative source ReadinessStatus already
 * reads) as part of this same transition, once evaluation succeeds, by
 * quest_evaluation_service.evaluate_attempt already having called
 * readiness_service.check_and_trigger before returning — so the value
 * read here is never stale relative to the Quest that was just
 * completed. It is folded into the "ready" phase atomically (not a
 * separate loading state layered on top) so the completion card never
 * flashes from "not ready" to "ready" as the fetch resolves. A failure
 * fetching it defaults to `readiness: null` (rendered as not-ready,
 * the safe default) rather than ever flipping the whole evaluation to
 * "failed" — the Quest's own successful completion must never be
 * hidden by a readiness-read failure.
 */
function QuestEvaluationFlow({ attemptId, employeeId }: { attemptId: string; employeeId: string }) {
  const [state, setState] = useState<EvaluationState>({ phase: "evaluating" });
  const [retryTick, setRetryTick] = useState(0);
  // Phase 6C: fetched once evaluation resolves — a fresh CapabilityProfile
  // may now exist, so this is the earliest point the recommendation can
  // reflect what this Quest just taught Buddy about the employee. Its
  // own failure (Phase 8H-5: now independently caught) only means no
  // recommendation card renders — it must never affect `state.phase`.
  const [nextQuest, setNextQuest] = useState<NextQuestResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    evaluateQuestAttempt(attemptId, employeeId)
      .then((result) => {
        if (cancelled) return;

        getNextQuest(employeeId)
          .then((next) => {
            if (!cancelled) setNextQuest(next);
          })
          .catch(() => {});

        return getReadinessSummary(employeeId)
          .catch(() => null)
          .then((readiness) => {
            if (cancelled) return;
            setState({ phase: "ready", result, readiness });
          });
      })
      .catch(() => {
        if (!cancelled) setState({ phase: "failed" });
      });

    return () => {
      cancelled = true;
    };
  }, [attemptId, employeeId, retryTick]);

  if (state.phase === "evaluating") {
    return (
      <div className="flex flex-col gap-6">
        <QuestBuddy phase="evaluating" />
        <Card>
          <div className="flex items-center justify-center gap-3 py-6 text-sm text-buddy-muted">
            <div className="h-8 w-8 shrink-0">
              <BuddyIllustration state="thinking" />
            </div>
            Buddy is reviewing your work…
          </div>
        </Card>
      </div>
    );
  }

  if (state.phase === "failed") {
    const retry = () => {
      setState({ phase: "evaluating" });
      setRetryTick((n) => n + 1);
    };
    return (
      <Card>
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 shrink-0">
            <BuddyIllustration state="thinking" />
          </div>
          <div className="flex-1">
            <p className="text-sm text-buddy-text-secondary">
              Buddy couldn&rsquo;t finish the review yet.
              <br />
              Your work is safely saved.
            </p>
            <Button className="mt-3" onClick={retry}>
              Try evaluation again
            </Button>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {state.result && <QuestCapabilityInsight result={state.result} />}
      {state.readiness?.ready ? (
        // Phase 8H-5: readiness is authoritative and already resolved —
        // this branch never re-derives it from nextQuest/capabilities/
        // attempt state, only reads the value the effect above fetched.
        <QuestReadyTransition />
      ) : (
        <>
          <QuestCompletion />
          {nextQuest && <QuestNextRecommendation response={nextQuest} />}
        </>
      )}
    </div>
  );
}

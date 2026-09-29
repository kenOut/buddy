"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { BuddySpeech } from "@/components/buddy/BuddySpeech";
import { FadeIn } from "@/components/animations/FadeIn";
import { SlideUp } from "@/components/animations/SlideUp";
import { StaggerChildren } from "@/components/animations/StaggerChildren";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { getNextQuest, getReadinessSummary } from "@/lib/capabilities";
import { getEmployeeQuests } from "@/lib/quests";
import { useOnboarding } from "@/lib/onboarding-context";
import type {
  EmployeeQuestSummary,
  EmployeeReadinessSummary,
  NextQuestResponse,
  QuestAttemptStatus,
} from "@/lib/types";

type LoadState =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | {
      phase: "ready";
      quests: EmployeeQuestSummary[];
      nextQuest: NextQuestResponse | null;
      readiness: EmployeeReadinessSummary | null;
    };

const STATUS_ACTION: Record<QuestAttemptStatus, string> = {
  NOT_STARTED: "Start Quest",
  IN_PROGRESS: "Continue Quest",
  SUBMITTED: "Awaiting evaluation",
  EVALUATING: "Awaiting evaluation",
  COMPLETED: "Completed",
};

const STATUS_TONE: Record<QuestAttemptStatus, "neutral" | "info" | "success" | "warning"> = {
  NOT_STARTED: "neutral",
  IN_PROGRESS: "info",
  SUBMITTED: "warning",
  EVALUATING: "warning",
  COMPLETED: "success",
};

/**
 * Phase 8H-4 — the employee's own Quest discovery surface, the launch
 * audit's final demo blocker: before this page existed, a Quest was
 * only reachable by already knowing its URL. Mirrors
 * DevelopmentJourneyScene's own loading/error/empty skeleton exactly
 * (same Buddy states, same Card/FadeIn/SlideUp primitives) rather than
 * introducing new visual language.
 */
export function YourQuestsScene() {
  const { bundle } = useOnboarding();
  const [state, setState] = useState<LoadState>({ phase: "loading" });
  const [retryTick, setRetryTick] = useState(0);

  useEffect(() => {
    if (!bundle) return;
    const employeeId = bundle.employee.id;
    let cancelled = false;
    // Resets state when retried so a stale error/empty view can't flash
    // while the new attempt is in flight.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState({ phase: "loading" });

    Promise.all([
      getEmployeeQuests(employeeId),
      getNextQuest(employeeId).catch(() => null),
      getReadinessSummary(employeeId).catch(() => null),
    ])
      .then(([quests, nextQuest, readiness]) => {
        if (cancelled) return;
        setState({ phase: "ready", quests, nextQuest, readiness });
      })
      .catch(() => {
        if (!cancelled) {
          setState({ phase: "error", message: "Couldn't load your Quests. Please try again." });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [bundle, retryTick]);

  if (!bundle) return null;

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 py-4">
      <FadeIn duration={0.5}>
        <div className="flex items-start gap-3 sm:gap-4">
          <div className="h-14 w-14 shrink-0">
            <BuddyIllustration state="guide" />
          </div>
          <BuddySpeech className="flex-1">
            <p className="font-heading text-lg font-bold text-buddy-navy">Your Quests</p>
            <p className="mt-1 text-buddy-text-secondary">
              These are the real-work challenges assigned to help you become ready to work.
            </p>
          </BuddySpeech>
        </div>
      </FadeIn>

      {state.phase === "loading" && (
        <div className="flex flex-col items-center gap-3 py-16 text-center">
          <div className="h-16 w-16">
            <BuddyIllustration state="thinking" />
          </div>
          <p className="text-sm text-buddy-muted">Buddy is pulling up your Quests…</p>
        </div>
      )}

      {state.phase === "error" && (
        <Card>
          <p role="alert" className="text-sm text-red-600">
            {state.message}
          </p>
          <Button className="mt-3" onClick={() => setRetryTick((n) => n + 1)}>
            Try again
          </Button>
        </Card>
      )}

      {state.phase === "ready" && <ReadyQuestList {...state} />}
    </div>
  );
}

function ReadyQuestList({
  quests,
  nextQuest,
  readiness,
}: {
  quests: EmployeeQuestSummary[];
  nextQuest: NextQuestResponse | null;
  readiness: EmployeeReadinessSummary | null;
}) {
  if (quests.length === 0) {
    return (
      <SlideUp duration={0.4}>
        <Card className="text-center">
          <div className="mx-auto h-16 w-16">
            <BuddyIllustration state="welcome" />
          </div>
          <h2 className="mt-4 font-heading text-lg font-bold text-buddy-navy">
            Nothing assigned yet.
          </h2>
          <p className="mx-auto mt-2 max-w-sm text-sm text-buddy-text-secondary">
            Your manager hasn&rsquo;t assigned you a Quest yet. Check back soon, or see your
            missions in the meantime.
          </p>
          <Link href="/onboarding/missions" className="mt-4 inline-block">
            <Button>See your missions</Button>
          </Link>
        </Card>
      </SlideUp>
    );
  }

  // Presentation-only grouping/ordering — required work shown first, per
  // the existing required_for_readiness signal (Phase 8H-3). Never a
  // second ranking: recommendation below is only ever the existing
  // /next-quest result, cross-referenced by id, not recomputed here.
  const required = quests.filter((q) => q.required_for_readiness);
  const optional = quests.filter((q) => !q.required_for_readiness);
  const recommendedId = nextQuest?.recommended_quest?.id ?? null;

  return (
    <>
      {readiness && readiness.required_quest_count > 0 && (
        <SlideUp duration={0.4}>
          <Card className="bg-buddy-cloud/60">
            <p className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">
              Required work
            </p>
            <p className="mt-1 font-heading text-lg font-bold text-buddy-navy">
              {readiness.completed_required_quest_count} of {readiness.required_quest_count}{" "}
              completed
            </p>
          </Card>
        </SlideUp>
      )}

      {required.length > 0 && (
        <section>
          <h2 className="font-heading text-lg font-bold text-buddy-navy">
            Required for readiness
          </h2>
          <StaggerChildren className="mt-3 flex flex-col gap-3" staggerDelay={0.06}>
            {required.map((quest) => (
              <QuestCard key={quest.id} quest={quest} isRecommended={quest.id === recommendedId} />
            ))}
          </StaggerChildren>
        </section>
      )}

      {optional.length > 0 && (
        <section>
          <h2 className="font-heading text-lg font-bold text-buddy-navy">Development</h2>
          <StaggerChildren className="mt-3 flex flex-col gap-3" staggerDelay={0.06}>
            {optional.map((quest) => (
              <QuestCard key={quest.id} quest={quest} isRecommended={quest.id === recommendedId} />
            ))}
          </StaggerChildren>
        </section>
      )}
    </>
  );
}

function QuestCard({ quest, isRecommended }: { quest: EmployeeQuestSummary; isRecommended: boolean }) {
  const status = quest.attempt_status ?? "NOT_STARTED";
  return (
    <Link
      href={`/onboarding/quests/${quest.id}`}
      className="block rounded-xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-buddy-primary"
    >
      <Card className="transition-colors hover:border-buddy-primary/50 hover:shadow-md">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              {quest.required_for_readiness && <Badge tone="coral">Required for readiness</Badge>}
              {isRecommended && <Badge tone="info">Recommended next</Badge>}
            </div>
            <p className="mt-1.5 font-medium text-buddy-text-primary">{quest.title}</p>
            {quest.description && (
              <p className="mt-1 text-sm text-buddy-text-secondary">{quest.description}</p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <Badge tone="neutral">{quest.quest_type.replace(/_/g, " ").toLowerCase()}</Badge>
              <Badge tone="neutral">{quest.difficulty.toLowerCase()}</Badge>
            </div>
          </div>
          <Badge tone={STATUS_TONE[status]} className="shrink-0">
            {STATUS_ACTION[status]}
          </Badge>
        </div>
      </Card>
    </Link>
  );
}

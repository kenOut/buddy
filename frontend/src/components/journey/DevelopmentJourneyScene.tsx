"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { FadeIn } from "@/components/animations/FadeIn";
import { SlideUp } from "@/components/animations/SlideUp";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { getNextQuest } from "@/lib/capabilities";
import { getDevelopmentJourney } from "@/lib/journey";
import { useOnboarding } from "@/lib/onboarding-context";
import type { DevelopmentJourneyResponse, NextQuestResponse } from "@/lib/types";
import { QuestNextRecommendation } from "@/components/quests/QuestNextRecommendation";
import { CurrentSnapshotCard } from "./CurrentSnapshotCard";
import { JourneyTimeline } from "./JourneyTimeline";

type LoadState =
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "ready"; journey: DevelopmentJourneyResponse; nextQuest: NextQuestResponse | null };

export function DevelopmentJourneyScene() {
  const { bundle } = useOnboarding();
  const [state, setState] = useState<LoadState>({ phase: "loading" });
  const [retryTick, setRetryTick] = useState(0);

  useEffect(() => {
    if (!bundle) return;
    const employeeId = bundle.employee.id;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState({ phase: "loading" });

    Promise.all([
      getDevelopmentJourney(employeeId),
      getNextQuest(employeeId).catch(() => null),
    ])
      .then(([journey, nextQuest]) => {
        if (cancelled) return;
        setState({ phase: "ready", journey, nextQuest });
      })
      .catch(() => {
        if (!cancelled) {
          setState({ phase: "error", message: "Couldn't load your development journey. Please try again." });
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
        <div className="text-center sm:text-left">
          <h1 className="font-heading text-2xl font-bold text-buddy-navy sm:text-3xl">
            Your Development Journey
          </h1>
          <p className="mt-2 text-sm text-buddy-text-secondary">
            Onboarding showed you your team and your role. This is what comes next — building real
            capability through practical work, with Buddy tracking the evidence as you go.
          </p>
        </div>
      </FadeIn>

      {state.phase === "loading" && (
        <div className="flex flex-col items-center gap-3 py-16 text-center">
          <div className="h-16 w-16">
            <BuddyIllustration state="thinking" />
          </div>
          <p className="text-sm text-buddy-muted">Buddy is putting your journey together…</p>
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

      {state.phase === "ready" && (
        <>
          {state.journey.items.length === 0 ? (
            <SlideUp duration={0.4}>
              <Card className="text-center">
                <div className="mx-auto h-16 w-16">
                  <BuddyIllustration state="welcome" />
                </div>
                <h2 className="mt-4 font-heading text-lg font-bold text-buddy-navy">
                  Your journey starts here.
                </h2>
                <p className="mx-auto mt-2 max-w-sm text-sm text-buddy-text-secondary">
                  Every Quest you complete is evidence Buddy uses to understand what you can do.
                  Complete your first one and this page will start filling in.
                </p>
                <Link href="/onboarding/missions" className="mt-4 inline-block">
                  <Button>See your missions</Button>
                </Link>
              </Card>
            </SlideUp>
          ) : (
            <>
              <CurrentSnapshotCard items={state.journey.items} />
              {state.nextQuest && (
                <QuestNextRecommendation response={state.nextQuest} showJourneyLink={false} />
              )}
              <JourneyTimeline items={state.journey.items} />
            </>
          )}
        </>
      )}
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { Celebration } from "@/components/animations/Celebration";
import { FadeIn } from "@/components/animations/FadeIn";
import { ProgressAnimation } from "@/components/animations/ProgressAnimation";
import { SlideUp } from "@/components/animations/SlideUp";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { WorkspaceAccessStatus } from "@/components/workspace/WorkspaceAccessStatus";
import { ApiError, api } from "@/lib/api";
import { useOnboarding } from "@/lib/onboarding-context";
import type { Assessment } from "@/lib/types";

export function CompletionScene() {
  const { bundle, resetDemo } = useOnboarding();
  const [assessment, setAssessment] = useState<Assessment | null>(null);

  useEffect(() => {
    if (!bundle) return;
    api
      .get<Assessment>(`/onboarding/assessments/${bundle.session.id}`)
      .then(setAssessment)
      .catch((err) => {
        if (!(err instanceof ApiError && err.status === 404)) throw err;
      });
  }, [bundle]);

  if (!bundle) return null;

  const firstName = bundle.employee.full_name.split(" ")[0];
  const completedMissions = bundle.mission_assignments.filter((a) => a.status === "completed").length;

  return (
    <div className="relative mx-auto flex max-w-2xl flex-col items-center gap-8 py-6 text-center sm:py-10">
      <Celebration />

      <FadeIn duration={0.9}>
        <div className="mx-auto h-32 w-32 sm:h-44 sm:w-44">
          <BuddyIllustration state="celebrating" label="Buddy celebrating" />
        </div>
      </FadeIn>

      <SlideUp delay={0.15} duration={0.5}>
        <p className="text-xs font-semibold uppercase tracking-widest text-buddy-primary">
          You&rsquo;re ready.
        </p>
        <h1 className="font-heading mt-2 text-3xl font-bold text-buddy-navy sm:text-5xl">
          Welcome to the team, {firstName}.
        </h1>
      </SlideUp>

      <SlideUp delay={0.3} duration={0.4} className="w-full max-w-sm">
        <div className="mb-2 flex items-center justify-between text-xs text-buddy-muted">
          <span>Onboarding complete</span>
          <span>100%</span>
        </div>
        <ProgressAnimation percent={100} height={10} />
      </SlideUp>

      <SlideUp delay={0.4} duration={0.4} className="grid w-full grid-cols-2 gap-4">
        <Card className="bg-buddy-cloud/60 text-center">
          <p className="font-heading text-2xl font-bold text-buddy-navy">
            {completedMissions}/{bundle.mission_assignments.length}
          </p>
          <p className="text-xs text-buddy-muted">missions complete</p>
        </Card>
        <Card className="bg-buddy-cloud/60 text-center">
          <p className="font-heading text-2xl font-bold text-buddy-navy">
            {assessment?.score != null ? `${assessment.score}%` : "—"}
          </p>
          <p className="text-xs text-buddy-muted">assessment score</p>
        </Card>
      </SlideUp>

      <SlideUp delay={0.55} duration={0.4} className="w-full">
        <WorkspaceAccessStatus employeeId={bundle.employee.id} />
      </SlideUp>

      <SlideUp delay={0.6} duration={0.4} className="flex w-full flex-wrap items-center justify-center gap-4">
        <Link
          href="/onboarding/quests"
          className="inline-flex items-center justify-center rounded-full bg-buddy-primary px-6 py-3 text-sm font-medium text-white shadow-lg shadow-buddy-primary/25 hover:bg-buddy-primary-dark"
        >
          Go to Your Quests
        </Link>
        <Link
          href="/onboarding/journey"
          className="text-sm font-medium text-buddy-primary hover:underline"
        >
          View your development journey →
        </Link>
      </SlideUp>

      <SlideUp delay={0.7} duration={0.4} className="mt-4 w-full border-t border-buddy-border pt-6">
        <DemoResetControl onReset={resetDemo} />
      </SlideUp>
    </div>
  );
}

/**
 * Presenter-only tooling, not part of the product an employee would ever
 * see for real — this whole app has exactly one identity to demo with,
 * so putting the demo back to day one has to be a click, not a script
 * someone runs for you. Two-step confirm (rather than a native
 * `confirm()` dialog, which nothing else here uses) guards against an
 * accidental click wiping the walkthrough mid-presentation.
 */
function DemoResetControl({ onReset }: { onReset: () => Promise<void> }) {
  const [phase, setPhase] = useState<"idle" | "confirming" | "resetting" | "error">("idle");

  if (phase === "resetting") {
    return (
      <p className="text-xs text-buddy-muted">Resetting the demo…</p>
    );
  }

  if (phase === "confirming") {
    return (
      <div className="flex flex-col items-center gap-2">
        <p className="text-xs text-buddy-muted">
          This clears all progress for the demo employee — missions, Quests, and workspace
          access. Reset it?
        </p>
        <div className="flex items-center gap-3">
          <Button variant="ghost" className="!px-3 !py-1.5 text-xs" onClick={() => setPhase("idle")}>
            Cancel
          </Button>
          <Button
            variant="secondary"
            className="!px-3 !py-1.5 text-xs"
            onClick={() => {
              setPhase("resetting");
              onReset().catch(() => setPhase("error"));
            }}
          >
            Yes, reset the demo
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-1.5">
      <button
        type="button"
        onClick={() => setPhase("confirming")}
        className="text-xs text-buddy-muted underline decoration-dotted underline-offset-4 hover:text-buddy-text-secondary"
      >
        Reset demo
      </button>
      {phase === "error" && (
        <p role="alert" className="text-xs text-red-600 dark:text-red-400">
          Couldn&rsquo;t reset the demo. Please try again.
        </p>
      )}
    </div>
  );
}

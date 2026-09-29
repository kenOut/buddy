"use client";

import Link from "next/link";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { SceneTransition } from "@/components/animations/SceneTransition";
import { ProgressIndicator } from "@/components/onboarding/ProgressIndicator";
import { ReadinessStatus } from "@/components/onboarding/ReadinessStatus";
import { Button } from "@/components/ui/Button";
import { useOnboarding } from "@/lib/onboarding-context";

export function OnboardingChrome({ children }: { children: React.ReactNode }) {
  const { bundle, loading, error, refetch } = useOnboarding();

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4">
        <div className="h-20 w-20">
          <BuddyIllustration state="thinking" />
        </div>
        <p className="text-sm text-buddy-muted">Loading your onboarding journey…</p>
      </div>
    );
  }

  if (error || !bundle) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
        <div className="h-20 w-20">
          <BuddyIllustration state="curious" />
        </div>
        <p className="max-w-sm text-sm text-buddy-muted">
          {error ?? "Something went wrong loading your onboarding session."}
        </p>
        <Button onClick={() => refetch()}>Try again</Button>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-6 px-4 py-6 sm:gap-8 sm:px-8 sm:py-10">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-4">
          <Link href="/" className="font-heading text-sm font-semibold tracking-tight text-buddy-navy">
            Buddy
          </Link>
          <Link
            href="/onboarding/quests"
            className="text-sm font-medium text-buddy-muted hover:text-buddy-primary"
          >
            Your Quests
          </Link>
        </div>
        <div className="flex items-center gap-3">
          <ReadinessStatus />
          <span className="text-xs text-buddy-muted">{bundle.organization.name}</span>
        </div>
      </header>

      <ProgressIndicator />

      <div className="flex-1">
        <SceneTransition>{children}</SceneTransition>
      </div>
    </div>
  );
}

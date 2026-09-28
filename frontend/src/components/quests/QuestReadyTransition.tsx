"use client";

import { useRouter } from "next/navigation";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SlideUp } from "@/components/animations/SlideUp";

/**
 * Phase 8H-5 — shown instead of QuestCompletion when the readiness
 * summary fetched right after evaluation (readiness_service.get_readiness_summary,
 * Phase 8H-1) reports `ready: true`. Readiness itself is never computed
 * here; this component only reacts to the value QuestWorkspace already
 * fetched and passes nothing of its own back into that computation.
 *
 * Navigation is an explicit click, not an automatic redirect — the
 * employee still gets to see this Quest's own completion/capability
 * feedback before being moved on, and a single Button click is
 * trivially safe to repeat (plain client-side navigation to an
 * idempotent read view, /onboarding/journey — no attempt, evaluation,
 * or journey record is created by visiting it).
 */
export function QuestReadyTransition() {
  const router = useRouter();

  return (
    <SlideUp duration={0.4}>
      <Card className="text-center">
        <div className="mx-auto h-16 w-16">
          <BuddyIllustration state="celebrating" />
        </div>
        <h2 className="mt-4 font-heading text-xl font-bold text-buddy-navy">You&rsquo;re ready.</h2>
        <p className="mx-auto mt-2 max-w-sm text-sm text-buddy-text-secondary">
          You&rsquo;ve completed everything required to get started. Buddy is moving you into your
          development journey.
        </p>
        <Button className="mt-4" onClick={() => router.push("/onboarding/journey")}>
          Continue to your Development Journey
        </Button>
      </Card>
    </SlideUp>
  );
}

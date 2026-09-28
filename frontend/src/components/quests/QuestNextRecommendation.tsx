import Link from "next/link";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { FadeIn } from "@/components/animations/FadeIn";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import type { NextQuestResponse } from "@/lib/types";

/**
 * Phase 6C Stage 9 — the employee-facing half of the adaptive loop.
 * Reuses the existing Buddy visual language exactly (same Card/FadeIn/
 * BuddyIllustration primitives as QuestCapabilityInsight and
 * CapabilityInsight's NextMissionCard) rather than introducing a new
 * dashboard. `response.recommended_quest` is the employee-safe
 * EmployeeQuest contract — nothing rendered here could ever carry
 * evaluation-criteria internals, because that type structurally cannot
 * hold them.
 */
export function QuestNextRecommendation({
  response,
  showJourneyLink = true,
}: {
  response: NextQuestResponse;
  /** Phase 6D: suppressed on the Development Journey page itself, which
   * already IS "your journey" — showing a link to itself there would be
   * a pointless self-reference. */
  showJourneyLink?: boolean;
}) {
  return (
    <FadeIn duration={0.4} delay={0.3}>
      <Card>
        <div className="flex items-start gap-3">
          <div className="h-10 w-10 shrink-0">
            <BuddyIllustration state="guide" />
          </div>
          <div className="flex-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
              What&rsquo;s next
            </p>

            {response.recommended_quest ? (
              <>
                <p className="mt-2 text-sm text-buddy-text-secondary">
                  Based on what I observed, here&rsquo;s what I&rsquo;d like you to try next.
                </p>
                <h3 className="mt-3 font-heading text-lg font-bold text-buddy-navy">
                  {response.recommended_quest.title}
                </h3>
                {/* Phase 8H-4/8H-3: independent of recommendation —
                    this Quest was selected by quest_recommendation.py's
                    capability-gap ranking, unrelated to whether it's
                    also required. Shown explicitly either way so a
                    recommended-but-optional Quest never reads as if
                    "required" was simply forgotten. */}
                <div className="mt-2">
                  <Badge tone={response.recommended_quest.required_for_readiness ? "info" : "neutral"}>
                    {response.recommended_quest.required_for_readiness
                      ? "Required for readiness"
                      : "Optional"}
                  </Badge>
                </div>
                {response.recommended_quest.description && (
                  <p className="mt-1 text-sm text-buddy-text-secondary">
                    {response.recommended_quest.description}
                  </p>
                )}
                {response.target_capabilities.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {response.target_capabilities.map((key) => (
                      <Badge key={key} tone="info">
                        {key.replace(/_/g, " ")}
                      </Badge>
                    ))}
                  </div>
                )}
                <p className="mt-3 text-sm text-buddy-text-primary">{response.reason}</p>
                <div className="mt-4 flex flex-wrap items-center gap-4">
                  <Link
                    href={`/onboarding/quests/${response.recommended_quest.id}`}
                    className="inline-flex items-center justify-center rounded-full bg-buddy-primary px-5 py-2.5 text-sm font-medium text-white shadow-lg shadow-buddy-primary/25 hover:bg-buddy-primary-dark"
                  >
                    Start &ldquo;{response.recommended_quest.title}&rdquo;
                  </Link>
                  {showJourneyLink && (
                    <Link
                      href="/onboarding/journey"
                      className="text-sm font-medium text-buddy-primary hover:underline"
                    >
                      View your full development journey →
                    </Link>
                  )}
                </div>
              </>
            ) : (
              <>
                <p className="mt-2 text-sm text-buddy-text-secondary">
                  You&rsquo;re caught up for now. There isn&rsquo;t another suitable Quest available
                  yet.
                </p>
                {showJourneyLink && (
                  <Link
                    href="/onboarding/journey"
                    className="mt-3 inline-block text-sm font-medium text-buddy-primary hover:underline"
                  >
                    View your full development journey →
                  </Link>
                )}
              </>
            )}
          </div>
        </div>
      </Card>
    </FadeIn>
  );
}

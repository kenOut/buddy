"use client";

import Link from "next/link";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { BuddySpeech } from "@/components/buddy/BuddySpeech";
import { MissionList } from "@/components/onboarding/MissionList";
import { SceneNav } from "@/components/onboarding/SceneNav";
import { useOnboarding } from "@/lib/onboarding-context";

export function MissionsScene() {
  const { bundle } = useOnboarding();
  if (!bundle) return null;

  const completed = bundle.mission_assignments.filter((a) => a.status === "completed").length;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 py-4">
      <div className="flex items-start gap-3 sm:gap-4">
        <div className="h-16 w-16 shrink-0">
          <BuddyIllustration state="encouraging" />
        </div>
        <BuddySpeech className="flex-1">
          <p className="font-heading text-lg font-bold text-buddy-navy">
            Okay. Enough introductions.
          </p>
          <p className="mt-1 text-buddy-text-secondary">Let&rsquo;s see what you can do.</p>
        </BuddySpeech>
      </div>

      <div>
        <h1 className="font-heading text-2xl font-bold text-buddy-navy sm:text-3xl">
          Your first missions
        </h1>
        <p className="mt-1 text-sm text-buddy-text-secondary">
          {completed} of {bundle.mission_assignments.length} complete — tap a status pill to
          advance it.
        </p>
      </div>

      <MissionList assignments={bundle.mission_assignments} />

      <p className="text-sm text-buddy-text-secondary">
        Missions are the checklist. For the real-work challenges that count toward readiness, see{" "}
        <Link href="/onboarding/quests" className="font-medium text-buddy-primary hover:underline">
          Your Quests
        </Link>
        .
      </p>

      <div className="flex items-center justify-between pt-2">
        <SceneNav />
      </div>
    </div>
  );
}

"use client";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { BuddySpeech } from "@/components/buddy/BuddySpeech";
import { TeamFormation } from "@/components/onboarding/TeamFormation";
import { SceneNav } from "@/components/onboarding/SceneNav";
import { useOnboarding } from "@/lib/onboarding-context";

export function TeamScene() {
  const { bundle } = useOnboarding();
  if (!bundle) return null;

  const { teammates, department, manager, supervisor } = bundle;

  // The backend's `teammates` list is everyone else in the department,
  // which includes the manager/supervisor — those get their own dedicated
  // scene (Reporting Line), so exclude them here to keep this scene to
  // genuine peers and avoid mislabeling a manager as "Teammate".
  const peers = teammates.filter(
    (t) => t.id !== manager?.id && t.id !== supervisor?.id
  );

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 py-4">
      <div className="flex items-start gap-3 sm:gap-4">
        <div className="h-14 w-14 shrink-0">
          <BuddyIllustration state="friendly" />
        </div>
        <BuddySpeech className="flex-1">
          <p className="font-heading text-lg font-bold text-buddy-navy">Meet your team</p>
          <p className="mt-1 text-buddy-text-secondary">
            These are the people you&rsquo;ll be working with in{" "}
            {department?.name ?? "your department"} — today&rsquo;s lineup.
          </p>
        </BuddySpeech>
      </div>

      {peers.length === 0 ? (
        <p className="text-sm text-buddy-muted">
          No teammates listed yet — you might be the first hire on this team!
        </p>
      ) : (
        <TeamFormation peers={peers} />
      )}

      <div className="flex items-center justify-between pt-2">
        <SceneNav />
      </div>
    </div>
  );
}

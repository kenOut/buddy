"use client";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { BuddySpeech } from "@/components/buddy/BuddySpeech";
import { StaggerChildren } from "@/components/animations/StaggerChildren";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { SceneNav } from "@/components/onboarding/SceneNav";
import { useOnboarding } from "@/lib/onboarding-context";
import { MISSION_TYPE_META } from "@/lib/missionTypes";
import type { MissionType } from "@/lib/types";

export function RoleScene() {
  const { bundle } = useOnboarding();
  if (!bundle) return null;

  const { role, employee, mission_assignments } = bundle;

  // Responsibility cards are derived from the real mix of assigned mission
  // types — not hardcoded per role/employee, and not a backend field.
  const presentTypes = Array.from(
    new Set(mission_assignments.map((a) => a.mission.mission_type))
  ) as MissionType[];

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 py-4">
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-buddy-primary">
          Your role
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-heading text-3xl font-bold text-buddy-navy sm:text-4xl">
            {role?.title ?? employee.job_title ?? "Team member"}
          </h1>
          {role?.level && <Badge tone="info">{role.level} level</Badge>}
        </div>
      </div>

      {role?.description && (
        <Card className="border-buddy-primary/20 bg-gradient-to-br from-buddy-primary/5 to-transparent">
          <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">Mission</p>
          <p className="mt-2 font-heading text-lg font-semibold text-buddy-navy sm:text-xl">
            &ldquo;{role.description}&rdquo;
          </p>
        </Card>
      )}

      {presentTypes.length > 0 && (
        <div>
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-buddy-muted">
            Responsibilities
          </p>
          <StaggerChildren className="grid grid-cols-1 gap-3 sm:grid-cols-2" staggerDelay={0.1}>
            {presentTypes.map((type) => {
              const meta = MISSION_TYPE_META[type];
              return (
                <Card key={type} className="flex items-center gap-3">
                  <span className="text-2xl">{meta.icon}</span>
                  <div>
                    <p className="font-medium text-buddy-text-primary">{meta.skill}</p>
                    <p className="text-xs text-buddy-text-secondary">{meta.label} work</p>
                  </div>
                </Card>
              );
            })}
          </StaggerChildren>
        </div>
      )}

      <div className="flex items-start gap-3 sm:gap-4">
        <div className="h-14 w-14 shrink-0">
          <BuddyIllustration state="friendly" />
        </div>
        <BuddySpeech className="flex-1">
          This is what your first few weeks will focus on — you&rsquo;ll see it all laid out as
          missions next.
        </BuddySpeech>
      </div>

      <div className="flex items-center justify-between pt-2">
        <SceneNav />
      </div>
    </div>
  );
}

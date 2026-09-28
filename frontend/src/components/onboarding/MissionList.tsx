"use client";

import Link from "next/link";
import { motion } from "motion/react";

import { StaggerChildren } from "@/components/animations/StaggerChildren";
import { Badge } from "@/components/ui/Badge";
import { MISSION_TYPE_META, difficultyTone, missionDifficulty } from "@/lib/missionTypes";
import type { MissionAssignment, MissionAssignmentStatus, MissionWorkspaceType } from "@/lib/types";

const statusTone: Record<MissionAssignmentStatus, "neutral" | "info" | "success" | "warning"> = {
  pending: "neutral",
  in_progress: "info",
  completed: "success",
  skipped: "warning",
};

/**
 * Not Started -> Start mission, In Progress -> Continue, Completed ->
 * Completed. This badge doubles as the card's call to action — clicking
 * anywhere on the card opens the mission workspace, where the actual
 * status change now happens (submitting real work through whichever of
 * the three workspace types the mission uses — investigation, quiz, or
 * reflection — never a bare status flip). There's no longer a
 * list-level mutation to error-handle here; that responsibility lives in
 * the workspace itself.
 */
const ctaLabel: Record<MissionAssignmentStatus, string> = {
  pending: "Start mission",
  in_progress: "Continue",
  completed: "Completed",
  skipped: "Start mission",
};

// Only the two "special" workspace kinds get a badge — reflection is the
// default, always-available shape, so leaving it unbadged avoids
// cluttering every single card with a label that's true of most of them.
const WORKSPACE_LABEL: Partial<Record<MissionWorkspaceType, string>> = {
  investigation: "Investigation",
  quiz: "Quiz",
};

export function MissionList({ assignments }: { assignments: MissionAssignment[] }) {
  const sorted = assignments.slice().sort((a, b) => a.mission.sort_order - b.mission.sort_order);

  return (
    <StaggerChildren className="space-y-3" itemClassName="" staggerDelay={0.08}>
      {sorted.map((assignment) => {
        const meta = MISSION_TYPE_META[assignment.mission.mission_type];
        const difficulty = missionDifficulty(assignment.mission.estimated_minutes);

        return (
          <Link
            key={assignment.id}
            href={`/onboarding/missions/${assignment.mission_id}`}
            className="block focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-buddy-primary rounded-xl"
          >
            <motion.div
              layout
              className="flex items-start justify-between gap-4 rounded-xl border border-buddy-border bg-buddy-surface p-4 shadow-sm transition-colors hover:border-buddy-primary/50 hover:shadow-md"
            >
              <div className="flex gap-3">
                <span className="text-xl" aria-hidden="true">
                  {meta.icon}
                </span>
                <div>
                  <p className="font-medium text-buddy-text-primary">{assignment.mission.title}</p>
                  {assignment.mission.description && (
                    <p className="mt-1 text-sm text-buddy-text-secondary">
                      {assignment.mission.description}
                    </p>
                  )}
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <Badge tone={difficultyTone(difficulty)}>{difficulty}</Badge>
                    <Badge tone="neutral">~{assignment.mission.estimated_minutes} min</Badge>
                    <Badge tone="info">{meta.skill}</Badge>
                    {WORKSPACE_LABEL[assignment.mission.workspace_type] && (
                      <Badge tone="neutral">{WORKSPACE_LABEL[assignment.mission.workspace_type]}</Badge>
                    )}
                    {assignment.mission.required && <Badge tone="coral">Required for readiness</Badge>}
                  </div>
                </div>
              </div>
              <Badge tone={statusTone[assignment.status]} className="shrink-0">
                {ctaLabel[assignment.status]}
              </Badge>
            </motion.div>
          </Link>
        );
      })}
    </StaggerChildren>
  );
}

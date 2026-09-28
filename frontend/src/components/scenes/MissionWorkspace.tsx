"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ApiError } from "@/lib/api";
import { createMissionAttempt, getMissionQuiz, getMissionScenario } from "@/lib/missionAttempts";
import { useOnboarding } from "@/lib/onboarding-context";
import type { MissionAssignment, MissionAttempt, MissionQuiz, MissionScenario } from "@/lib/types";
import { InvestigationWorkspace } from "@/components/scenes/mission-workspace/InvestigationWorkspace";
import { QuizWorkspace } from "@/components/scenes/mission-workspace/QuizWorkspace";
import { ReflectionWorkspace } from "@/components/scenes/mission-workspace/ReflectionWorkspace";

type LoadState =
  | { phase: "loading" }
  | { phase: "not-assigned" }
  | { phase: "error"; message: string }
  | { phase: "reflection"; assignment: MissionAssignment; attempt: MissionAttempt }
  | { phase: "quiz"; assignment: MissionAssignment; quiz: MissionQuiz; attempt: MissionAttempt }
  | { phase: "investigation"; assignment: MissionAssignment; scenario: MissionScenario; attempt: MissionAttempt };

/**
 * Every Mission now has a real workspace_type (investigation/quiz/
 * reflection) driving which component renders — no more probing
 * /missions/{id}/scenario and inferring "no scenario means simple" from
 * a 404. The Mission itself already says which kind of work environment
 * it needs (see backend/app/models/mission.py's own docstring), so this
 * just fetches whatever that kind additionally needs (a scenario, a
 * quiz, or nothing) and creates/resumes the one MissionAttempt row every
 * workspace type shares.
 */
export function MissionWorkspace({ missionId }: { missionId: string }) {
  const { bundle, updateAssignment } = useOnboarding();
  const [state, setState] = useState<LoadState>({ phase: "loading" });
  // Bumping this re-runs the load effect below without needing to change
  // `missionId` or `bundle` — the retry button's only job.
  const [retryTick, setRetryTick] = useState(0);

  useEffect(() => {
    if (!bundle) return;

    const assignment = bundle.mission_assignments.find((a) => a.mission_id === missionId);
    if (!assignment) {
      // Synchronous early exit — nothing async to defer this into.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setState({ phase: "not-assigned" });
      return;
    }

    let cancelled = false;
    // Resets state when `missionId` changes so stale data from a previous
    // mission can't flash while the new one loads.
    setState({ phase: "loading" });

    const syncInProgress = (attempt: MissionAttempt) => {
      // Creating/resuming an attempt always bumps a `pending` assignment
      // to `in_progress` server-side (mission_attempt_service.py). Sync
      // that locally too — otherwise the Missions list keeps showing
      // "Start mission" instead of "Continue" until a full reload,
      // since nothing else refetches the bundle after this.
      if (assignment.status === "pending") {
        updateAssignment({ ...assignment, status: "in_progress" });
      }
      return attempt;
    };

    const onFailure = (err: unknown) => {
      if (cancelled) return;
      if (err instanceof ApiError && err.status === 403) {
        setState({ phase: "not-assigned" });
      } else {
        setState({ phase: "error", message: "Couldn't load this mission. Please try again." });
      }
    };

    if (assignment.mission.workspace_type === "investigation") {
      Promise.all([
        getMissionScenario(missionId, bundle.employee.id),
        createMissionAttempt(missionId, bundle.employee.id).then(syncInProgress),
      ])
        .then(([scenario, attempt]) => {
          if (cancelled) return;
          setState({ phase: "investigation", assignment, scenario, attempt });
        })
        .catch(onFailure);
    } else if (assignment.mission.workspace_type === "quiz") {
      Promise.all([
        getMissionQuiz(missionId, bundle.employee.id),
        createMissionAttempt(missionId, bundle.employee.id).then(syncInProgress),
      ])
        .then(([quiz, attempt]) => {
          if (cancelled) return;
          setState({ phase: "quiz", assignment, quiz, attempt });
        })
        .catch(onFailure);
    } else {
      createMissionAttempt(missionId, bundle.employee.id)
        .then(syncInProgress)
        .then((attempt) => {
          if (cancelled) return;
          setState({ phase: "reflection", assignment, attempt });
        })
        .catch(onFailure);
    }

    return () => {
      cancelled = true;
    };
  }, [bundle, missionId, updateAssignment, retryTick]);

  if (!bundle) return null;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 py-4">
      <Link
        href="/onboarding/missions"
        className="text-sm text-buddy-muted hover:text-buddy-text-primary"
      >
        ← Back to missions
      </Link>

      {state.phase === "loading" && (
        <p className="text-sm text-buddy-muted">Loading mission…</p>
      )}

      {state.phase === "not-assigned" && (
        <Card>
          <p className="text-sm text-buddy-text-secondary">
            This mission isn&rsquo;t assigned to you, or couldn&rsquo;t be found.
          </p>
        </Card>
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

      {state.phase === "reflection" && (
        <ReflectionWorkspace
          assignment={state.assignment}
          attempt={state.attempt}
          employeeId={bundle.employee.id}
          onSubmitted={(attempt) => {
            if (attempt.passed && state.assignment.status !== "completed") {
              updateAssignment({ ...state.assignment, status: "completed" });
            }
          }}
        />
      )}

      {state.phase === "quiz" && (
        <QuizWorkspace
          assignment={state.assignment}
          quiz={state.quiz}
          attempt={state.attempt}
          employeeId={bundle.employee.id}
          onSubmitted={(attempt) => {
            if (attempt.passed && state.assignment.status !== "completed") {
              updateAssignment({ ...state.assignment, status: "completed" });
            }
          }}
        />
      )}

      {state.phase === "investigation" && (
        <InvestigationWorkspace
          assignment={state.assignment}
          scenario={state.scenario}
          attempt={state.attempt}
          employeeId={bundle.employee.id}
          onSubmitted={(attempt) => {
            if (attempt.passed && state.assignment.status !== "completed") {
              updateAssignment({ ...state.assignment, status: "completed" });
            }
          }}
        />
      )}
    </div>
  );
}

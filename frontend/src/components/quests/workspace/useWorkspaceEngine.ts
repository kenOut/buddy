"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";
import { submitQuestAttempt, updateQuestAttempt } from "@/lib/quests";
import type { EmployeeQuest, QuestAttempt } from "@/lib/types";
import type { SaveState } from "@/components/quests/QuestWorkForm";
import type { WorkspaceDraft, WorkspaceLifecycleState } from "./types";

const AUTOSAVE_DEBOUNCE_MS = 700;

type SaveOverrides = Partial<{
  findings: string;
  reasoning: string;
  solution: string;
  completed_task_ids: string[];
  workspace: { type: string; payload: Record<string, unknown> };
}>;

function extractDetail(err: unknown): string | null {
  if (err instanceof ApiError) {
    try {
      const parsed = JSON.parse(err.message) as { detail?: string };
      return parsed.detail ?? null;
    } catch {
      return null;
    }
  }
  return null;
}

/**
 * The Workspace Engine, Stage 1's hook-based implementation (a
 * hook/context shape is cleaner here than a class — this is React state
 * plus a handful of API calls, not an object with independent identity).
 *
 * Owns everything the Stage 1 contract puts on the Engine side of the
 * boundary for an in-progress attempt: autosave debouncing, the PATCH/
 * submit API calls, and the "in_progress" → "submitting" lifecycle
 * transition. It knows nothing about workspace_type — every field here
 * is the same findings/reasoning/solution/completed_task_ids/workspace
 * envelope regardless of which Workspace component is mounted above it,
 * and it never branches on `quest.workspace_type` beyond passing it
 * through unread inside the `workspace` envelope it writes.
 *
 * This is a line-for-line extraction of what QuestWorkspaceContent used
 * to own directly before Stage 1 — behavior-preserving, not a redesign.
 *
 * Phase 7 Stage 3 — text fields and the workspace payload share a single
 * debounce timer and land in one PATCH per autosave cycle (not two
 * independent ones). Two concurrent PATCHes to the same attempt row can
 * race: the backend's `update_submission` reads-merges-writes per
 * request, so if a workspace-payload PATCH and a text-field PATCH are
 * both in flight at once, whichever commits last can overwrite the
 * other's contribution with a merge based on stale data. A single
 * combined save removes the race outright rather than trying to order
 * around it.
 */
export function useWorkspaceEngine({
  quest,
  attempt: initialAttempt,
  employeeId,
}: {
  quest: EmployeeQuest;
  attempt: QuestAttempt;
  employeeId: string;
}) {
  const [attempt, setAttempt] = useState(initialAttempt);
  const [findings, setFindings] = useState(attempt.submission.findings ?? "");
  const [reasoning, setReasoning] = useState(attempt.submission.reasoning ?? "");
  const [solution, setSolution] = useState(attempt.submission.solution ?? "");
  const [completedTaskIds, setCompletedTaskIds] = useState<Set<string>>(
    () => new Set(attempt.submission.completed_task_ids ?? [])
  );
  const [workspacePayload, setWorkspacePayload] = useState<Record<string, unknown> | null>(
    () => attempt.submission.workspace?.payload ?? null
  );

  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fieldsRef = useRef({ findings, reasoning, solution });
  const workspacePayloadRef = useRef(workspacePayload);
  // Whether the workspace payload has changed since it was last included
  // in a save — a Generic Workspace never sets this, so its autosave
  // cycle never gains a `workspace` field it didn't have before.
  const workspaceDirtyRef = useRef(false);

  useEffect(() => {
    fieldsRef.current = { findings, reasoning, solution };
  }, [findings, reasoning, solution]);

  useEffect(() => {
    workspacePayloadRef.current = workspacePayload;
  }, [workspacePayload]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const saveWork = useCallback(
    (overrides: SaveOverrides = {}) => {
      setSaveState("saving");
      return updateQuestAttempt(attempt.id, { employee_id: employeeId, ...overrides })
        .then((updated) => {
          setAttempt(updated);
          setSaveState("saved");
          return updated;
        })
        .catch((err) => {
          setSaveState("error");
          throw err;
        });
    },
    [attempt.id, employeeId]
  );

  const buildPendingOverrides = useCallback((): SaveOverrides => {
    const f = fieldsRef.current;
    const overrides: SaveOverrides = { findings: f.findings, reasoning: f.reasoning, solution: f.solution };
    if (workspaceDirtyRef.current) {
      overrides.workspace = { type: quest.workspace_type, payload: workspacePayloadRef.current ?? {} };
      workspaceDirtyRef.current = false;
    }
    return overrides;
  }, [quest.workspace_type]);

  const scheduleSave = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      saveWork(buildPendingOverrides()).catch(() => {
        // Save status already reflects the failure; retry is user-driven.
      });
    }, AUTOSAVE_DEBOUNCE_MS);
  }, [saveWork, buildPendingOverrides]);

  const onFieldChange = (field: "findings" | "reasoning" | "solution", value: string) => {
    if (field === "findings") setFindings(value);
    if (field === "reasoning") setReasoning(value);
    if (field === "solution") setSolution(value);
    scheduleSave();
  };

  const onWorkspacePayloadChange = (payload: Record<string, unknown>) => {
    setWorkspacePayload(payload);
    workspaceDirtyRef.current = true;
    scheduleSave();
  };

  const onRetrySave = () => {
    const f = fieldsRef.current;
    const overrides: SaveOverrides = { findings: f.findings, reasoning: f.reasoning, solution: f.solution };
    if (workspacePayloadRef.current) {
      overrides.workspace = { type: quest.workspace_type, payload: workspacePayloadRef.current };
    }
    saveWork(overrides).catch(() => {});
  };

  const onCompleteTask = (taskId: string, done: boolean) => {
    const next = new Set(completedTaskIds);
    if (done) next.add(taskId);
    else next.delete(taskId);
    setCompletedTaskIds(next);
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    // Folds in whatever text/workspace changes were still pending behind
    // the debounce, rather than discarding them — a task checkbox click
    // moments after editing a hypothesis must not silently drop that edit.
    const overrides = buildPendingOverrides();
    overrides.completed_task_ids = Array.from(next);
    saveWork(overrides).catch(() => {});
  };

  const requiredTasks = quest.tasks.filter((t) => t.required);
  const allRequiredDone = requiredTasks.every((t) => completedTaskIds.has(t.id));
  const hasWork = Boolean(findings.trim() || reasoning.trim() || solution.trim());
  const canSubmit = allRequiredDone && hasWork;

  const onSubmit = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
        debounceRef.current = null;
        await saveWork(buildPendingOverrides());
      }
      const result = await submitQuestAttempt(attempt.id, employeeId);
      setAttempt(result);
    } catch (err) {
      const detail = extractDetail(err);
      setSubmitError(
        detail ??
          (err instanceof ApiError
            ? "Couldn't submit your quest. Please try again."
            : "Network error — couldn't reach the server. Please try again.")
      );
    } finally {
      setSubmitting(false);
    }
  };

  const lifecycle: WorkspaceLifecycleState = submitting ? "submitting" : "in_progress";

  const draft: WorkspaceDraft = { findings, reasoning, solution, completedTaskIds, workspacePayload };

  return {
    attempt,
    lifecycle,
    draft,
    saveState,
    submitError,
    canSubmit,
    requiredTasks,
    onFieldChange,
    onWorkspacePayloadChange,
    onCompleteTask,
    onRetrySave,
    onSubmit,
  };
}

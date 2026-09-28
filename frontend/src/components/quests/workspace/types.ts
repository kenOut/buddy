import type { ReactElement } from "react";

import type { EmployeeQuest, QuestAttempt, QuestTaskItem, QuestWorkspaceType } from "@/lib/types";
import type { SaveState } from "@/components/quests/QuestWorkForm";

/**
 * Phase 7 Stage 1 — the Workspace Engine/Workspace contract.
 *
 * `WorkspaceType` is an alias, not a second source of truth: it reuses
 * `QuestWorkspaceType` exactly as the backend validates it and the API
 * already returns it (Quest.workspace_type / EmployeeQuest.workspace_type).
 */
export type WorkspaceType = QuestWorkspaceType;

/**
 * What is happening to the attempt right now — decided entirely by the
 * Engine (useWorkspaceEngine). A Workspace reads this to know how to
 * render (e.g. disable inputs while submitting) but never sets it: a
 * Workspace has no way to independently decide "submitted" or
 * "evaluating" — those only happen once the Engine's own submit()/
 * evaluate() calls resolve, outside the Workspace entirely (see
 * QuestWorkspace.tsx's QuestEvaluationFlow, which a Workspace never
 * renders itself).
 */
export type WorkspaceLifecycleState = "in_progress" | "submitting";

/**
 * The employee-editable slice of QuestAttempt.submission, in the shape
 * the Engine hands to a Workspace. `workspacePayload` is the additive
 * envelope's payload half (the `type` half is implied by whichever
 * Workspace is mounted) — present so a specialized Workspace can carry
 * its own structured state without the generic findings/reasoning/
 * solution/completedTaskIds fields ever changing shape.
 */
export interface WorkspaceDraft {
  findings: string;
  reasoning: string;
  solution: string;
  completedTaskIds: Set<string>;
  workspacePayload: Record<string, unknown> | null;
}

/** Not yet surfaced by any Workspace in Stage 1 (neither Generic nor the
 * Troubleshoot placeholder fails in a way that needs it), but declared
 * now per the Stage 1 contract's Error Boundary so the Engine has a
 * single typed shape to hand back once a Workspace does need one. */
export interface WorkspaceError {
  code: string;
  message: string;
  retryable: boolean;
}

/** Everything a Workspace needs to know about the Quest it's rendering.
 * No API client, no navigation function — a Workspace that wanted to
 * fetch or navigate would need something this interface deliberately
 * doesn't provide. */
export interface WorkspaceContext {
  quest: EmployeeQuest;
  attempt: QuestAttempt;
  employeeId: string;
}

/**
 * The full prop contract every registry entry's component receives.
 * A Workspace renders challenge/evidence/tasks/its own interaction/
 * review and calls back through onFieldChange/onCompleteTask/onSubmit —
 * it must never call the Quest/QuestAttempt API directly, decide
 * submitted/evaluating/completed itself, or navigate away from the page.
 */
export interface WorkspaceProps {
  context: WorkspaceContext;
  lifecycle: WorkspaceLifecycleState;
  draft: WorkspaceDraft;
  saveState: SaveState;
  submitError: string | null;
  canSubmit: boolean;
  requiredTasks: QuestTaskItem[];
  onFieldChange: (field: "findings" | "reasoning" | "solution", value: string) => void;
  onWorkspacePayloadChange: (payload: Record<string, unknown>) => void;
  onCompleteTask: (taskId: string, done: boolean) => void;
  onRetrySave: () => void;
  onSubmit: () => void;
}

export type WorkspaceComponent = (props: WorkspaceProps) => ReactElement | null;

/**
 * The boundary a registry entry crosses between the Engine's canonical
 * wire shape (the `workspace` envelope inside QuestAttempt.submission)
 * and whatever a specific Workspace wants as its own payload shape.
 * Both Stage 1 entries use the identity adapter below — neither Generic
 * nor the Troubleshoot placeholder has a custom payload yet — but the
 * seam exists so a future specialized Workspace can introduce one
 * without the Engine, or this interface, changing at all.
 */
export interface WorkspaceSubmissionAdapter {
  fromSubmission: (payload: Record<string, unknown> | undefined | null) => Record<string, unknown> | null;
  toSubmission: (payload: Record<string, unknown>) => Record<string, unknown>;
}

export interface WorkspaceRegistryEntry {
  component: WorkspaceComponent;
  adapter: WorkspaceSubmissionAdapter;
}

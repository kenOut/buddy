import { GenericWorkspace } from "./GenericWorkspace";
import { TroubleshootWorkspace } from "./TroubleshootWorkspace";
import type { WorkspaceRegistryEntry, WorkspaceType } from "./types";

const IDENTITY_ADAPTER = {
  fromSubmission: (payload: Record<string, unknown> | undefined | null) => payload ?? null,
  toSubmission: (payload: Record<string, unknown>) => payload,
};

/**
 * The workspace registry. Keyed by the same `workspace_type` values the
 * backend validates against (WORKSPACE_TYPES) and already returns on
 * every Quest/EmployeeQuest — not a second, frontend-only enum. Adding a
 * new specialized Workspace later means adding one entry here; nothing
 * about QuestWorkspace.tsx, useWorkspaceEngine, or any existing entry
 * changes.
 */
const WORKSPACE_REGISTRY: Partial<Record<WorkspaceType, WorkspaceRegistryEntry>> = {
  TROUBLESHOOT: { component: TroubleshootWorkspace, adapter: IDENTITY_ADAPTER },
};

const GENERIC_ENTRY: WorkspaceRegistryEntry = { component: GenericWorkspace, adapter: IDENTITY_ADAPTER };

/**
 * Resolves a Quest's workspace_type — an untrusted string as far as the
 * frontend type system is concerned, even though the backend already
 * validates it against WORKSPACE_TYPES before it's ever returned — to
 * the registry entry that should render it. A value with no registered
 * entry (including any future workspace_type this build hasn't shipped
 * support for) falls back to the Generic entry rather than crashing:
 * the boundary check is this lookup, not a cast.
 */
export function resolveWorkspace(workspaceType: string): WorkspaceRegistryEntry {
  return WORKSPACE_REGISTRY[workspaceType as WorkspaceType] ?? GENERIC_ENTRY;
}

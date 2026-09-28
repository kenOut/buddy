import { QuestHeader } from "@/components/quests/QuestHeader";
import { StandardStepFlow } from "./StandardStepFlow";
import type { WorkspaceProps } from "./types";

/**
 * Stage 1's behavior-preserving extraction of the original QuestWorkspace
 * body. This is the registry's fallback entry (resolveWorkspace.ts) —
 * every workspace_type without a specialized entry renders through here,
 * exactly as every Quest did before this refactor existed. It owns only
 * its own step navigation (inside StandardStepFlow); everything about
 * the attempt itself — autosave, submit, lifecycle — arrives through
 * WorkspaceProps from the Engine.
 */
export function GenericWorkspace(props: WorkspaceProps) {
  return (
    <div className="flex flex-col gap-6">
      <QuestHeader quest={props.context.quest} />
      <StandardStepFlow {...props} />
    </div>
  );
}

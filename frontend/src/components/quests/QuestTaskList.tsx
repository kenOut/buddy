import clsx from "clsx";

import { Badge } from "@/components/ui/Badge";
import type { QuestTaskItem, QuestTaskType } from "@/lib/types";

const TASK_TYPE_LABELS: Record<QuestTaskType, string> = {
  INVESTIGATE: "Investigate",
  ANALYZE: "Analyze",
  DESIGN: "Design",
  BUILD: "Build",
  FIX: "Fix",
  EXPLAIN: "Explain",
  CREATE: "Create",
  OTHER: "Task",
};

/** Renders whatever QuestTask rows exist, in sort_order — never a
 * hard-coded task list (Stage 4 spec §12). */
export function QuestTaskList({
  tasks,
  completedIds,
  onToggle,
  disabled,
}: {
  tasks: QuestTaskItem[];
  completedIds: Set<string>;
  onToggle: (taskId: string, done: boolean) => void;
  disabled?: boolean;
}) {
  const sorted = tasks.slice().sort((a, b) => a.sort_order - b.sort_order);

  return (
    <ul className="space-y-2.5">
      {sorted.map((task, i) => {
        const done = completedIds.has(task.id);
        return (
          <li
            key={task.id}
            className={clsx(
              "flex items-start gap-3 rounded-lg border border-buddy-border px-3 py-2.5 transition-colors",
              done && "border-buddy-aurora/40 bg-buddy-aurora/5"
            )}
          >
            <input
              type="checkbox"
              id={`quest-task-${task.id}`}
              checked={done}
              onChange={(e) => onToggle(task.id, e.target.checked)}
              disabled={disabled}
              className="mt-1 h-4 w-4 shrink-0 accent-[var(--buddy-primary)] disabled:opacity-60"
            />
            <label htmlFor={`quest-task-${task.id}`} className={clsx("flex-1", !disabled && "cursor-pointer")}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">
                  Task {i + 1}
                </span>
                <Badge tone="info">{TASK_TYPE_LABELS[task.task_type] ?? task.task_type}</Badge>
                <Badge tone={task.required ? "coral" : "neutral"}>
                  {task.required ? "Required" : "Optional"}
                </Badge>
              </div>
              <p className="mt-1 font-medium text-buddy-text-primary">{task.title}</p>
              {task.description && (
                <p className="mt-0.5 text-sm text-buddy-text-secondary">{task.description}</p>
              )}
            </label>
          </li>
        );
      })}
    </ul>
  );
}

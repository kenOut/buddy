import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import type { QuestSubmissionData, QuestTaskItem } from "@/lib/types";

export function QuestReview({
  submission,
  requiredTasks,
  completedIds,
  onSubmit,
  submitting,
  submitError,
  canSubmit,
}: {
  submission: QuestSubmissionData;
  requiredTasks: QuestTaskItem[];
  completedIds: Set<string>;
  onSubmit: () => void;
  submitting: boolean;
  submitError: string | null;
  canSubmit: boolean;
}) {
  return (
    <div className="space-y-4">
      <Card>
        <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
          Your work
        </p>
        <ReviewField label="Findings" value={submission.findings} />
        <ReviewField label="Reasoning" value={submission.reasoning} />
        <ReviewField label="Solution" value={submission.solution} />
      </Card>

      {requiredTasks.length > 0 && (
        <Card>
          <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
            Required tasks
          </p>
          <ul className="mt-2 space-y-1 text-sm">
            {requiredTasks.map((task) => {
              const done = completedIds.has(task.id);
              return (
                <li key={task.id} className={done ? "text-emerald-700 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}>
                  <span aria-hidden="true">{done ? "✓ " : "○ "}</span>
                  {task.title}
                  {!done && <span className="sr-only"> — not yet completed</span>}
                </li>
              );
            })}
          </ul>
        </Card>
      )}

      {submitError && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {submitError}
        </p>
      )}

      <Button onClick={onSubmit} disabled={!canSubmit || submitting} className="w-full">
        {submitting ? "Submitting…" : "Submit quest"}
      </Button>
      {!canSubmit && !submitting && (
        <p className="text-center text-xs text-buddy-muted">
          Complete the required tasks and record at least one of your findings, reasoning, or
          solution before submitting.
        </p>
      )}
    </div>
  );
}

function ReviewField({ label, value }: { label: string; value?: string }) {
  return (
    <div className="mt-3">
      <p className="text-xs font-medium text-buddy-muted">{label}</p>
      <p className="mt-1 text-sm text-buddy-text-primary">
        {value?.trim() ? value : <span className="text-buddy-muted">Not recorded</span>}
      </p>
    </div>
  );
}

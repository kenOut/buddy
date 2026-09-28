import { Card } from "@/components/ui/Card";
import type { EmployeeQuest } from "@/lib/types";

/** Challenge content comes entirely from the backend Quest data
 * (description + task titles/descriptions) — nothing is invented on the
 * frontend (Stage 4 spec §9). */
export function QuestChallenge({ quest }: { quest: EmployeeQuest }) {
  const sortedTasks = quest.tasks.slice().sort((a, b) => a.sort_order - b.sort_order);

  return (
    <div className="space-y-4">
      <Card>
        <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
          The challenge
        </p>
        <p className="mt-2 text-sm text-buddy-text-primary">
          {quest.description ?? "Your manager hasn't added a description for this quest yet."}
        </p>
      </Card>

      {sortedTasks.length > 0 && (
        <Card>
          <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
            What you&rsquo;re expected to produce
          </p>
          <ol className="mt-3 space-y-2">
            {sortedTasks.map((task, i) => (
              <li key={task.id} className="flex gap-3 text-sm">
                <span className="shrink-0 font-mono text-xs text-buddy-muted">{i + 1}.</span>
                <span className="text-buddy-text-primary">
                  {task.title}
                  {!task.required && (
                    <span className="ml-2 text-xs text-buddy-muted">(optional)</span>
                  )}
                </span>
              </li>
            ))}
          </ol>
        </Card>
      )}
    </div>
  );
}

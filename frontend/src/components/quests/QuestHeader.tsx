import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import type { EmployeeQuest, QuestDifficulty, QuestType } from "@/lib/types";

const QUEST_TYPE_LABELS: Record<QuestType, string> = {
  INVESTIGATE: "Investigate",
  TROUBLESHOOT: "Troubleshoot",
  FIX: "Fix",
  BUILD: "Build",
  DESIGN: "Design",
  ANALYZE: "Analyze",
  CREATE_SOLUTION: "Create a solution",
  OTHER: "Open-ended",
};

const DIFFICULTY_TONE: Record<QuestDifficulty, "neutral" | "info" | "warning" | "coral"> = {
  EASY: "neutral",
  MEDIUM: "info",
  HARD: "warning",
  EXPERT: "coral",
};

/** Employee-safe header — renders only fields EmployeeQuest actually
 * carries. There is nothing here that could show expected_answer/
 * expected_behavior/reference_solution because the type this component
 * accepts has no such field at all. */
export function QuestHeader({ quest }: { quest: EmployeeQuest }) {
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="info">{QUEST_TYPE_LABELS[quest.quest_type] ?? quest.quest_type}</Badge>
        <Badge tone={DIFFICULTY_TONE[quest.difficulty] ?? "neutral"}>
          {quest.difficulty.toLowerCase()}
        </Badge>
      </div>
      <h1 className="mt-3 font-heading text-xl font-bold text-buddy-navy sm:text-2xl">
        {quest.title}
      </h1>
      {quest.description && (
        <p className="mt-2 text-sm text-buddy-text-secondary">{quest.description}</p>
      )}
    </Card>
  );
}

import type { MissionType } from "@/lib/types";

interface MissionTypeMeta {
  icon: string;
  label: string;
  /** Framed as a "skill tested" / responsibility tag — derived presentation,
   * not backend data. Generic per mission_type, never per-employee. */
  skill: string;
}

export const MISSION_TYPE_META: Record<MissionType, MissionTypeMeta> = {
  setup: { icon: "🛠️", label: "Setup", skill: "Environment & Tooling" },
  reading: { icon: "📖", label: "Reading", skill: "Systems Knowledge" },
  meeting: { icon: "🤝", label: "Meeting", skill: "Communication" },
  training: { icon: "🎓", label: "Training", skill: "Compliance" },
  task: { icon: "🚀", label: "Task", skill: "Delivery & Execution" },
};

export type Difficulty = "Easy" | "Medium" | "Advanced";

const DIFFICULTY_TONE: Record<Difficulty, "success" | "warning" | "coral"> = {
  Easy: "success",
  Medium: "warning",
  Advanced: "coral",
};

/** Presentational-only heuristic — never persisted, never sent to the backend. */
export function missionDifficulty(estimatedMinutes: number): Difficulty {
  if (estimatedMinutes <= 20) return "Easy";
  if (estimatedMinutes <= 40) return "Medium";
  return "Advanced";
}

export function difficultyTone(difficulty: Difficulty) {
  return DIFFICULTY_TONE[difficulty];
}

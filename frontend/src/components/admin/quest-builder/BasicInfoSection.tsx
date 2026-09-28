"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { updateQuest } from "@/lib/admin-quests";
import { api, ApiError } from "@/lib/api";
import type { Department, Project, QuestDetail, QuestDifficulty, QuestType } from "@/lib/types";
import { getQuestTypeHint } from "@/lib/questTypeHints";
import { SaveStateIndicator, type BuilderSaveState } from "./SaveStateIndicator";

const QUEST_TYPES: QuestType[] = [
  "INVESTIGATE",
  "TROUBLESHOOT",
  "FIX",
  "BUILD",
  "DESIGN",
  "ANALYZE",
  "CREATE_SOLUTION",
  "OTHER",
];

const DIFFICULTIES: QuestDifficulty[] = ["EASY", "MEDIUM", "HARD", "EXPERT"];

export function BasicInfoSection({
  quest,
  editable,
  onSaved,
}: {
  quest: QuestDetail;
  editable: boolean;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(quest.title);
  const [questType, setQuestType] = useState<QuestType>(quest.quest_type);
  const [difficulty, setDifficulty] = useState<QuestDifficulty>(quest.difficulty);
  const [departmentId, setDepartmentId] = useState(quest.department_id ?? "");
  const [projectId, setProjectId] = useState(quest.project_id ?? "");
  const [departments, setDepartments] = useState<Department[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [saveState, setSaveState] = useState<BuilderSaveState>("idle");

  useEffect(() => {
    setTitle(quest.title);
    setQuestType(quest.quest_type);
    setDifficulty(quest.difficulty);
    setDepartmentId(quest.department_id ?? "");
    setProjectId(quest.project_id ?? "");
  }, [quest]);

  useEffect(() => {
    api.get<Department[]>("/departments").then(setDepartments);
  }, []);

  useEffect(() => {
    if (!departmentId) {
      setProjects([]);
      return;
    }
    api
      .get<Project[]>(`/projects?department_id=${encodeURIComponent(departmentId)}`)
      .then(setProjects);
  }, [departmentId]);

  const handleSave = async () => {
    setSaveState("saving");
    try {
      await updateQuest(quest.id, {
        title,
        quest_type: questType,
        difficulty,
        department_id: departmentId || null,
        project_id: projectId || null,
      });
      setSaveState("saved");
      onSaved();
    } catch (err) {
      setSaveState("error");
      const detail =
        err instanceof ApiError
          ? (() => {
              try {
                return (JSON.parse(err.message) as { detail?: string }).detail;
              } catch {
                return null;
              }
            })()
          : null;
      if (detail) console.error(detail);
    }
  };

  return (
    <Card className="space-y-4">
      <div>
        <label htmlFor="bi-title" className="mb-1 block text-sm font-medium text-foreground">
          Title
        </label>
        <input
          id="bi-title"
          value={title}
          disabled={!editable}
          onChange={(e) => setTitle(e.target.value)}
          className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm disabled:opacity-60"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label htmlFor="bi-type" className="mb-1 block text-sm font-medium text-foreground">
            Quest type
          </label>
          <select
            id="bi-type"
            value={questType}
            disabled={!editable}
            onChange={(e) => setQuestType(e.target.value as QuestType)}
            className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm disabled:opacity-60"
          >
            {QUEST_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-buddy-muted">{getQuestTypeHint(questType).taskHint}</p>
        </div>
        <div>
          <label
            htmlFor="bi-difficulty"
            className="mb-1 block text-sm font-medium text-foreground"
          >
            Difficulty
          </label>
          <select
            id="bi-difficulty"
            value={difficulty}
            disabled={!editable}
            onChange={(e) => setDifficulty(e.target.value as QuestDifficulty)}
            className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm disabled:opacity-60"
          >
            {DIFFICULTIES.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label htmlFor="bi-dept" className="mb-1 block text-sm font-medium text-foreground">
            Department
          </label>
          <select
            id="bi-dept"
            value={departmentId}
            disabled={!editable}
            onChange={(e) => {
              setDepartmentId(e.target.value);
              setProjectId("");
            }}
            className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm disabled:opacity-60"
          >
            <option value="">None</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="bi-project" className="mb-1 block text-sm font-medium text-foreground">
            Project
          </label>
          <select
            id="bi-project"
            value={projectId}
            disabled={!editable || !departmentId}
            onChange={(e) => setProjectId(e.target.value)}
            className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm disabled:opacity-60"
          >
            <option value="">None</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {editable && (
        <div className="flex items-center gap-3 pt-2">
          <Button onClick={handleSave} disabled={saveState === "saving"}>
            Save
          </Button>
          <SaveStateIndicator state={saveState} onRetry={handleSave} />
        </div>
      )}
    </Card>
  );
}

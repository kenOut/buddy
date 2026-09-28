"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { createQuest } from "@/lib/admin-quests";
import { api } from "@/lib/api";
import type { Department, Project, QuestType, QuestWorkspaceType } from "@/lib/types";

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

const WORKSPACE_TYPES: QuestWorkspaceType[] = [
  "INVESTIGATION",
  "DESIGN",
  "BUILD",
  "FIX",
  "ANALYSIS",
  "GENERAL",
  "TROUBLESHOOT",
];

export default function NewQuestPage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [questType, setQuestType] = useState<QuestType>("INVESTIGATE");
  const [workspaceType, setWorkspaceType] = useState<QuestWorkspaceType>("INVESTIGATION");
  const [departmentId, setDepartmentId] = useState<string>("");
  const [projectId, setProjectId] = useState<string>("");
  const [departments, setDepartments] = useState<Department[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<Department[]>("/departments").then(setDepartments);
  }, []);

  useEffect(() => {
    if (!departmentId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setProjects([]);
      setProjectId("");
      return;
    }
    api
      .get<Project[]>(`/projects?department_id=${encodeURIComponent(departmentId)}`)
      .then(setProjects);
  }, [departmentId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("Give this Quest a title before continuing.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const quest = await createQuest({
        title: title.trim(),
        quest_type: questType,
        workspace_type: workspaceType,
        department_id: departmentId || null,
        project_id: projectId || null,
      });
      router.push(`/admin/quests/${quest.id}`);
    } catch {
      setError("Couldn't create this Quest. Please try again.");
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">New Quest</h1>
        <p className="mt-1 text-sm text-buddy-muted">
          Start a real-work challenge — you&rsquo;ll fill in the rest in the Quest Builder.
        </p>
      </div>

      <Card>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div>
            <label htmlFor="title" className="mb-1 block text-sm font-medium text-foreground">
              Title
            </label>
            <input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Diagnose a checkout latency spike"
              className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="quest_type" className="mb-1 block text-sm font-medium text-foreground">
                Quest type
              </label>
              <select
                id="quest_type"
                value={questType}
                onChange={(e) => setQuestType(e.target.value as QuestType)}
                className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
              >
                {QUEST_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label
                htmlFor="workspace_type"
                className="mb-1 block text-sm font-medium text-foreground"
              >
                Workspace layout
              </label>
              <select
                id="workspace_type"
                value={workspaceType}
                onChange={(e) => setWorkspaceType(e.target.value as QuestWorkspaceType)}
                className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
              >
                {WORKSPACE_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label
                htmlFor="department"
                className="mb-1 block text-sm font-medium text-foreground"
              >
                Department (optional)
              </label>
              <select
                id="department"
                value={departmentId}
                onChange={(e) => setDepartmentId(e.target.value)}
                className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
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
              <label htmlFor="project" className="mb-1 block text-sm font-medium text-foreground">
                Project (optional)
              </label>
              <select
                id="project"
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                disabled={!departmentId}
                className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm disabled:opacity-50"
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

          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => router.push("/admin/quests")}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Creating…" : "Create draft"}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

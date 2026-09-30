"use client";

import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { api } from "@/lib/api";
import type { Department, Mission, MissionType, MissionWorkspaceType } from "@/lib/types";

const MISSION_TYPES: MissionType[] = ["task", "reading", "setup", "meeting", "training"];

const WORKSPACE_TYPES: { value: MissionWorkspaceType; label: string }[] = [
  { value: "reflection", label: "Reflection (freeform, works for any mission)" },
  { value: "quiz", label: "Quiz (pick from titles with content already written)" },
  { value: "investigation", label: "Investigation (pick from titles with a scenario already written)" },
];

export function NewMissionModal({
  departments,
  onClose,
  onCreated,
}: {
  departments: Department[];
  onClose: () => void;
  onCreated: (mission: Mission) => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [departmentId, setDepartmentId] = useState(departments[0]?.id ?? "");
  const [missionType, setMissionType] = useState<MissionType>("task");
  const [workspaceType, setWorkspaceType] = useState<MissionWorkspaceType>("reflection");
  const [estimatedMinutes, setEstimatedMinutes] = useState(15);
  const [required, setRequired] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Quiz/investigation content is static, server-side code keyed by
  // exact mission title (see missions.py's own docstring on this
  // endpoint) — picking from titles real content already exists for,
  // instead of typing one free-hand, makes a 404-on-open mission
  // impossible to create rather than just discouraged.
  const [contentTitles, setContentTitles] = useState<{ quiz: string[]; investigation: string[] }>({
    quiz: [],
    investigation: [],
  });
  useEffect(() => {
    api
      .get<{ quiz: string[]; investigation: string[] }>("/missions/workspace-content-titles")
      .then(setContentTitles)
      .catch(() => {});
  }, []);

  function handleWorkspaceTypeChange(next: MissionWorkspaceType) {
    setWorkspaceType(next);
    // A title picked for one workspace type is meaningless for another
    // (quiz/investigation titles come from two disjoint content sets,
    // and reflection needs no matching content at all) — clear it
    // rather than carry over a stale, possibly-invalid value.
    setTitle("");
  }

  const titleOptions = workspaceType === "quiz" ? contentTitles.quiz : contentTitles.investigation;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const mission = await api.post<Mission>("/missions", {
        department_id: departmentId || null,
        title: title.trim(),
        description: description.trim() || null,
        mission_type: missionType,
        estimated_minutes: estimatedMinutes,
        required,
        workspace_type: workspaceType,
      });
      onCreated(mission);
      onClose();
    } catch {
      setError("Couldn't create the mission. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-20 flex items-start justify-center overflow-y-auto bg-black/30 px-4 py-10"
      onClick={onClose}
    >
      <div className="w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <Card>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-foreground">New mission</h2>
              <p className="mt-1 text-sm text-buddy-muted">
                Add an onboarding task for a department&rsquo;s new hires.
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="text-buddy-muted hover:text-foreground"
            >
              ✕
            </button>
          </div>

          <form onSubmit={handleSubmit} className="mt-4 space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="mission-title" className="text-sm font-medium text-foreground">
                Title
              </label>
              {workspaceType === "reflection" ? (
                <input
                  id="mission-title"
                  autoFocus
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm focus:border-buddy-primary focus:outline-none"
                  placeholder="e.g. Set up your local dev environment"
                />
              ) : (
                <select
                  id="mission-title"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm focus:border-buddy-primary focus:outline-none"
                >
                  <option value="" disabled>
                    {titleOptions.length === 0
                      ? `No ${workspaceType} content written yet`
                      : `Select a title with ${workspaceType} content written…`}
                  </option>
                  {titleOptions.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div className="space-y-1.5">
              <label htmlFor="mission-department" className="text-sm font-medium text-foreground">
                Department
              </label>
              <select
                id="mission-department"
                required
                value={departmentId}
                onChange={(e) => setDepartmentId(e.target.value)}
                className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm focus:border-buddy-primary focus:outline-none"
              >
                {departments.map((department) => (
                  <option key={department.id} value={department.id}>
                    {department.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label htmlFor="mission-type" className="text-sm font-medium text-foreground">
                  Type
                </label>
                <select
                  id="mission-type"
                  value={missionType}
                  onChange={(e) => setMissionType(e.target.value as MissionType)}
                  className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm capitalize focus:border-buddy-primary focus:outline-none"
                >
                  {MISSION_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="mission-minutes" className="text-sm font-medium text-foreground">
                  Est. minutes
                </label>
                <input
                  id="mission-minutes"
                  type="number"
                  min={1}
                  required
                  value={estimatedMinutes}
                  onChange={(e) => setEstimatedMinutes(Number(e.target.value))}
                  className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm focus:border-buddy-primary focus:outline-none"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="mission-description" className="text-sm font-medium text-foreground">
                Description <span className="text-buddy-muted">(optional)</span>
              </label>
              <textarea
                id="mission-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm focus:border-buddy-primary focus:outline-none"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="mission-workspace" className="text-sm font-medium text-foreground">
                Work environment
              </label>
              <select
                id="mission-workspace"
                value={workspaceType}
                onChange={(e) => handleWorkspaceTypeChange(e.target.value as MissionWorkspaceType)}
                className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm focus:border-buddy-primary focus:outline-none"
              >
                {WORKSPACE_TYPES.map((w) => (
                  <option key={w.value} value={w.value}>
                    {w.label}
                  </option>
                ))}
              </select>
              {workspaceType !== "reflection" && titleOptions.length === 0 && (
                <p className="text-xs text-buddy-coral">
                  No {workspaceType} content has been written yet, so there&rsquo;s nothing to pick a
                  title from. Choose Reflection, or add content in{" "}
                  {workspaceType === "quiz" ? "mission_quizzes.py" : "mission_scenarios.py"} first.
                </p>
              )}
            </div>

            <label className="flex items-start gap-2 text-sm text-foreground">
              <input
                type="checkbox"
                checked={required}
                onChange={(e) => setRequired(e.target.checked)}
                className="mt-0.5"
              />
              <span>
                Required for readiness
                <span className="block text-xs text-buddy-muted">
                  Employees in this department can&rsquo;t be marked ready until this mission is
                  complete.
                </span>
              </span>
            </label>

            {error && <p className="text-sm text-buddy-coral">{error}</p>}

            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="secondary" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" disabled={submitting || !title.trim() || !departmentId}>
                {submitting ? "Creating…" : "Create mission"}
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </div>
  );
}

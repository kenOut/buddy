"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import {
  archiveQuest,
  createQuestAssignment,
  deleteQuestAssignment,
  getPublishReadiness,
  listQuestAssignments,
  publishQuest,
  updateQuestAssignment,
} from "@/lib/admin-quests";
import { api, ApiError } from "@/lib/api";
import type {
  Department,
  Employee,
  QuestAssignment,
  QuestAssignmentType,
  QuestDetail,
  QuestQualityValidation,
  Role,
} from "@/lib/types";
import type { BuilderSectionKey } from "./BuilderNav";
import { QuestQualityPanel } from "./QuestQualityPanel";

export function AssignPublishSection({
  quest,
  onChanged,
  onNavigateToSection,
}: {
  quest: QuestDetail;
  onChanged: () => void;
  onNavigateToSection: (section: BuilderSectionKey) => void;
}) {
  const [assignments, setAssignments] = useState<QuestAssignment[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [readiness, setReadiness] = useState<QuestQualityValidation | null>(null);

  const [assignmentType, setAssignmentType] = useState<QuestAssignmentType>("EMPLOYEE");
  const [targetId, setTargetId] = useState("");
  const [newAssignmentRequired, setNewAssignmentRequired] = useState(false);
  const [newAssignmentMinimumScore, setNewAssignmentMinimumScore] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [requiredError, setRequiredError] = useState<string | null>(null);
  const [togglingRequiredId, setTogglingRequiredId] = useState<string | null>(null);
  const [minimumScoreDraft, setMinimumScoreDraft] = useState<Record<string, string>>({});
  const [savingMinimumScoreId, setSavingMinimumScoreId] = useState<string | null>(null);
  const [publishError, setPublishError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadAssignments = () => listQuestAssignments(quest.id).then(setAssignments);
  const loadReadiness = () => getPublishReadiness(quest.id).then(setReadiness);

  useEffect(() => {
    loadAssignments();
    loadReadiness();
    api.get<Employee[]>("/employees").then(setEmployees);
    api.get<Department[]>("/departments").then(setDepartments);
    api.get<Role[]>("/roles").then(setRoles);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quest.id, quest.status]);

  const employeeName = (id: string) => employees.find((e) => e.id === id)?.full_name ?? id;
  const departmentName = (id: string) => departments.find((d) => d.id === id)?.name ?? id;
  const roleName = (id: string) => roles.find((r) => r.id === id)?.title ?? id;

  const handleAddAssignment = async () => {
    if (!targetId) {
      setError("Choose who this Quest should be assigned to.");
      return;
    }
    setError(null);
    try {
      const minimumScore =
        newAssignmentRequired && newAssignmentMinimumScore.trim()
          ? Number(newAssignmentMinimumScore)
          : null;
      const payload =
        assignmentType === "EMPLOYEE"
          ? {
              assignment_type: assignmentType,
              employee_id: targetId,
              required: newAssignmentRequired,
              minimum_score: minimumScore,
            }
          : assignmentType === "DEPARTMENT"
            ? {
                assignment_type: assignmentType,
                department_id: targetId,
                required: newAssignmentRequired,
                minimum_score: minimumScore,
              }
            : {
                assignment_type: assignmentType,
                role_id: targetId,
                required: newAssignmentRequired,
                minimum_score: minimumScore,
              };
      await createQuestAssignment(quest.id, payload);
      setTargetId("");
      setNewAssignmentRequired(false);
      setNewAssignmentMinimumScore("");
      await loadAssignments();
      await loadReadiness();
      onChanged();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError("This target is already assigned to this Quest.");
      } else {
        setError("Couldn't create this assignment.");
      }
    }
  };

  const handleToggleActive = async (assignment: QuestAssignment) => {
    try {
      await updateQuestAssignment(quest.id, assignment.id, { active: !assignment.active });
      await loadAssignments();
      await loadReadiness();
      onChanged();
    } catch {
      setError("Couldn't update this assignment.");
    }
  };

  const handleToggleRequired = async (assignment: QuestAssignment) => {
    setRequiredError(null);
    setTogglingRequiredId(assignment.id);
    try {
      // Turning "required" off makes any configured threshold moot —
      // clear it server-side too, rather than leaving a dangling
      // minimum_score on a now-optional assignment (readiness_service
      // would simply ignore it either way, since only required items
      // are ever threshold-checked, but leaving stale configuration
      // around invites confusion the next time this is turned back on).
      const patch = assignment.required
        ? { required: false, minimum_score: null }
        : { required: true };
      await updateQuestAssignment(quest.id, assignment.id, patch);
      setMinimumScoreDraft((prev) => ({ ...prev, [assignment.id]: "" }));
      await loadAssignments();
      await loadReadiness();
      onChanged();
    } catch {
      setRequiredError("Couldn't update whether this assignment is required.");
    } finally {
      setTogglingRequiredId(null);
    }
  };

  const handleSaveMinimumScore = async (assignment: QuestAssignment) => {
    const draft = minimumScoreDraft[assignment.id];
    const minimumScore = draft === undefined || draft.trim() === "" ? null : Number(draft);
    if (minimumScore === (assignment.minimum_score ?? null)) return;
    setRequiredError(null);
    setSavingMinimumScoreId(assignment.id);
    try {
      await updateQuestAssignment(quest.id, assignment.id, { minimum_score: minimumScore });
      await loadAssignments();
      await loadReadiness();
      onChanged();
    } catch {
      setRequiredError("Couldn't update the minimum score for this assignment.");
    } finally {
      setSavingMinimumScoreId(null);
    }
  };

  const handleDeleteAssignment = async (assignmentId: string) => {
    try {
      await deleteQuestAssignment(quest.id, assignmentId);
      await loadAssignments();
      await loadReadiness();
      onChanged();
    } catch {
      setError("Couldn't remove this assignment.");
    }
  };

  const handlePublish = async () => {
    setBusy(true);
    setPublishError(null);
    try {
      await publishQuest(quest.id);
      onChanged();
      await loadReadiness();
    } catch (err) {
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
      setPublishError(detail ?? "Couldn't publish this Quest.");
    } finally {
      setBusy(false);
    }
  };

  const handleArchive = async () => {
    setBusy(true);
    setPublishError(null);
    try {
      await archiveQuest(quest.id);
      onChanged();
    } catch {
      setPublishError("Couldn't archive this Quest.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card className="space-y-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
            Assignments
          </p>
          <p className="mt-1 text-sm text-buddy-muted">
            Who can see and attempt this Quest. Assignments stay editable even after the Quest
            is published — the challenge content itself does not.
          </p>
        </div>

        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {error}
          </p>
        )}
        {requiredError && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {requiredError}
          </p>
        )}

        <ul className="space-y-2">
          {assignments.map((assignment) => (
            <li
              key={assignment.id}
              className="flex flex-col gap-3 rounded-lg border border-buddy-border px-4 py-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-sm">
                  <Badge tone="info">{assignment.assignment_type}</Badge>
                  <span className="font-medium text-foreground">
                    {assignment.assignment_type === "EMPLOYEE" &&
                      employeeName(assignment.employee_id ?? "")}
                    {assignment.assignment_type === "DEPARTMENT" &&
                      departmentName(assignment.department_id ?? "")}
                    {assignment.assignment_type === "ROLE" && roleName(assignment.role_id ?? "")}
                  </span>
                  {!assignment.active && <Badge tone="neutral">inactive</Badge>}
                  {assignment.required && <Badge tone="coral">required</Badge>}
                  {assignment.required && assignment.minimum_score !== null && (
                    <Badge tone="info">min {assignment.minimum_score}%</Badge>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => handleToggleActive(assignment)}
                    className="text-xs font-medium text-buddy-primary hover:underline"
                  >
                    {assignment.active ? "Deactivate" : "Activate"}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDeleteAssignment(assignment.id)}
                    className="text-xs font-medium text-red-600 dark:text-red-400 hover:underline"
                  >
                    Remove
                  </button>
                </div>
              </div>

              <label
                htmlFor={`required-${assignment.id}`}
                className="flex items-start gap-2 rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-buddy-primary"
              >
                <input
                  id={`required-${assignment.id}`}
                  type="checkbox"
                  checked={assignment.required}
                  disabled={togglingRequiredId === assignment.id}
                  onChange={() => handleToggleRequired(assignment)}
                  className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--buddy-primary)] disabled:cursor-not-allowed disabled:opacity-50"
                />
                <span>
                  <span className="font-medium text-foreground">Required for readiness</span>
                  <span className="block text-xs text-buddy-muted">
                    Employees must complete this Quest before Buddy marks them ready to work.
                  </span>
                </span>
              </label>

              {assignment.required && (
                <div className="flex items-center gap-2 pl-6">
                  <label htmlFor={`min-score-${assignment.id}`} className="text-sm text-foreground">
                    Minimum score
                  </label>
                  <input
                    id={`min-score-${assignment.id}`}
                    type="number"
                    min={0}
                    max={100}
                    placeholder="Completion only"
                    value={minimumScoreDraft[assignment.id] ?? assignment.minimum_score?.toString() ?? ""}
                    disabled={savingMinimumScoreId === assignment.id}
                    onChange={(e) =>
                      setMinimumScoreDraft((prev) => ({ ...prev, [assignment.id]: e.target.value }))
                    }
                    onBlur={() => handleSaveMinimumScore(assignment)}
                    className="w-32 rounded-lg border border-buddy-border bg-buddy-surface px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
                  />
                  <span className="text-xs text-buddy-muted">
                    {savingMinimumScoreId === assignment.id ? "Saving…" : "Leave blank for completion only"}
                  </span>
                </div>
              )}
            </li>
          ))}
          {assignments.length === 0 && (
            <li className="text-sm text-buddy-muted">No assignments yet.</li>
          )}
        </ul>

        <div className="flex flex-col gap-3 rounded-lg border border-buddy-border p-4">
          <div className="flex flex-wrap items-center gap-3">
          <select
            value={assignmentType}
            onChange={(e) => {
              setAssignmentType(e.target.value as QuestAssignmentType);
              setTargetId("");
            }}
            className="rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
          >
            <option value="EMPLOYEE">Employee</option>
            <option value="DEPARTMENT">Department</option>
            <option value="ROLE">Role</option>
          </select>

          {assignmentType === "EMPLOYEE" && (
            <select
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              className="min-w-[200px] rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
            >
              <option value="">Choose an employee…</option>
              {employees.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.full_name}
                </option>
              ))}
            </select>
          )}
          {assignmentType === "DEPARTMENT" && (
            <select
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              className="min-w-[200px] rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
            >
              <option value="">Choose a department…</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          )}
          {assignmentType === "ROLE" && (
            <select
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              className="min-w-[200px] rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
            >
              <option value="">Choose a role…</option>
              {roles.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.title}
                </option>
              ))}
            </select>
          )}

          <Button variant="secondary" onClick={handleAddAssignment}>
            + Assign
          </Button>
        </div>

          <label
            htmlFor="new-assignment-required"
            className="flex items-start gap-2 self-start rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-buddy-primary"
          >
            <input
              id="new-assignment-required"
              type="checkbox"
              checked={newAssignmentRequired}
              onChange={(e) => {
                setNewAssignmentRequired(e.target.checked);
                if (!e.target.checked) setNewAssignmentMinimumScore("");
              }}
              className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--buddy-primary)]"
            />
            <span>
              <span className="font-medium text-foreground">Required for readiness</span>
              <span className="block text-xs text-buddy-muted">
                Employees must complete this Quest before Buddy marks them ready to work.
              </span>
            </span>
          </label>

          {newAssignmentRequired && (
            <div className="flex items-center gap-2 self-start pl-1">
              <label htmlFor="new-assignment-minimum-score" className="text-sm text-foreground">
                Minimum score
              </label>
              <input
                id="new-assignment-minimum-score"
                type="number"
                min={0}
                max={100}
                placeholder="Completion only"
                value={newAssignmentMinimumScore}
                onChange={(e) => setNewAssignmentMinimumScore(e.target.value)}
                className="w-32 rounded-lg border border-buddy-border bg-buddy-surface px-3 py-1.5 text-sm"
              />
            </div>
          )}
        </div>
      </Card>

      <QuestQualityPanel validation={readiness} onNavigateToSection={onNavigateToSection} />

      <Card className="space-y-4">
        {publishError && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {publishError}
          </p>
        )}

        <div className="flex gap-3">
          {quest.status === "DRAFT" && (
            <Button onClick={handlePublish} disabled={busy || !(readiness?.ready ?? false)}>
              Publish Quest
            </Button>
          )}
          {quest.status === "PUBLISHED" && (
            <Button variant="secondary" onClick={handleArchive} disabled={busy}>
              Archive Quest
            </Button>
          )}
          {quest.status === "ARCHIVED" && (
            <p className="text-sm text-buddy-muted">This Quest is archived.</p>
          )}
        </div>
      </Card>
    </div>
  );
}

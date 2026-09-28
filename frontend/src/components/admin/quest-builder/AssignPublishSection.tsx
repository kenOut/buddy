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
  const [error, setError] = useState<string | null>(null);
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
      const payload =
        assignmentType === "EMPLOYEE"
          ? { assignment_type: assignmentType, employee_id: targetId }
          : assignmentType === "DEPARTMENT"
            ? { assignment_type: assignmentType, department_id: targetId }
            : { assignment_type: assignmentType, role_id: targetId };
      await createQuestAssignment(quest.id, payload);
      setTargetId("");
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
      await updateQuestAssignment(quest.id, assignment.id, !assignment.active);
      await loadAssignments();
      await loadReadiness();
      onChanged();
    } catch {
      setError("Couldn't update this assignment.");
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
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}

        <ul className="space-y-2">
          {assignments.map((assignment) => (
            <li
              key={assignment.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-buddy-border px-4 py-3"
            >
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
                  className="text-xs font-medium text-red-600 hover:underline"
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
          {assignments.length === 0 && (
            <li className="text-sm text-buddy-muted">No assignments yet.</li>
          )}
        </ul>

        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-buddy-border p-4">
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
      </Card>

      <QuestQualityPanel validation={readiness} onNavigateToSection={onNavigateToSection} />

      <Card className="space-y-4">
        {publishError && (
          <p role="alert" className="text-sm text-red-600">
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

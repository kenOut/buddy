"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import {
  createQuestEvidence,
  createQuestTask,
  deleteQuestEvidence,
  deleteQuestTask,
  updateQuestEvidence,
  updateQuestTask,
} from "@/lib/admin-quests";
import type {
  QuestDetail,
  QuestEvidenceItem,
  QuestEvidenceType,
  QuestTaskItem,
  QuestTaskType,
} from "@/lib/types";
import { getQuestTypeHint } from "@/lib/questTypeHints";

const TASK_TYPES: QuestTaskType[] = [
  "INVESTIGATE",
  "ANALYZE",
  "DESIGN",
  "BUILD",
  "FIX",
  "EXPLAIN",
  "CREATE",
  "OTHER",
];

const EVIDENCE_TYPES: QuestEvidenceType[] = [
  "METRICS",
  "LOGS",
  "SERVICES",
  "TIMELINE",
  "SCREENSHOT",
  "DOCUMENT",
  "CODE",
  "DATASET",
  "TEXT",
  "OTHER",
];

export function WorkEvidenceSection({
  quest,
  editable,
  onChanged,
}: {
  quest: QuestDetail;
  editable: boolean;
  onChanged: () => void;
}) {
  return (
    <div className="space-y-6">
      <TasksPanel quest={quest} editable={editable} onChanged={onChanged} />
      <EvidencePanel quest={quest} editable={editable} onChanged={onChanged} />
    </div>
  );
}

// ---- Tasks ----

function TasksPanel({
  quest,
  editable,
  onChanged,
}: {
  quest: QuestDetail;
  editable: boolean;
  onChanged: () => void;
}) {
  const hint = getQuestTypeHint(quest.quest_type);
  const tasks = quest.tasks.slice().sort((a, b) => a.sort_order - b.sort_order);
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [taskType, setTaskType] = useState<QuestTaskType>("INVESTIGATE");
  const [required, setRequired] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const resetForm = () => {
    setTitle("");
    setDescription("");
    setTaskType("INVESTIGATE");
    setRequired(true);
    setAdding(false);
  };

  const handleAdd = async () => {
    if (!title.trim()) {
      setError("Give this task a title.");
      return;
    }
    setError(null);
    try {
      await createQuestTask(quest.id, {
        title: title.trim(),
        description: description.trim() || null,
        task_type: taskType,
        required,
        sort_order: tasks.length,
      });
      resetForm();
      onChanged();
    } catch {
      setError("Couldn't add this task.");
    }
  };

  const handleDelete = async (taskId: string) => {
    try {
      await deleteQuestTask(quest.id, taskId);
      onChanged();
    } catch {
      setError("Couldn't remove this task.");
    }
  };

  const move = async (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= tasks.length) return;
    const a = tasks[index];
    const b = tasks[target];
    try {
      await Promise.all([
        updateQuestTask(quest.id, a.id, { sort_order: b.sort_order }),
        updateQuestTask(quest.id, b.id, { sort_order: a.sort_order }),
      ]);
      onChanged();
    } catch {
      setError("Couldn't reorder tasks.");
    }
  };

  return (
    <Card className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
            Tasks
          </p>
          <p className="mt-1 text-sm text-buddy-muted">
            The concrete actions an employee should take. Add at least two.
          </p>
          <p className="mt-1 text-xs text-buddy-primary">{hint.taskHint}</p>
        </div>
        {editable && !adding && (
          <Button variant="secondary" onClick={() => setAdding(true)}>
            + Add task
          </Button>
        )}
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      <ul className="space-y-2">
        {tasks.map((task, i) => (
          <TaskRow
            key={task.id}
            task={task}
            index={i}
            count={tasks.length}
            editable={editable}
            onDelete={() => handleDelete(task.id)}
            onMove={(dir) => move(i, dir)}
          />
        ))}
        {tasks.length === 0 && !adding && (
          <li className="text-sm text-buddy-muted">No tasks yet.</li>
        )}
      </ul>

      {adding && (
        <div className="space-y-3 rounded-lg border border-buddy-border p-4">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Task title"
            className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
          />
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description (optional)"
            rows={2}
            className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
          />
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={taskType}
              onChange={(e) => setTaskType(e.target.value as QuestTaskType)}
              className="rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
            >
              {TASK_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-2 text-sm text-foreground">
              <input
                type="checkbox"
                checked={required}
                onChange={(e) => setRequired(e.target.checked)}
              />
              Required
            </label>
          </div>
          <div className="flex gap-2">
            <Button onClick={handleAdd}>Add task</Button>
            <Button variant="ghost" onClick={resetForm}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

function TaskRow({
  task,
  index,
  count,
  editable,
  onDelete,
  onMove,
}: {
  task: QuestTaskItem;
  index: number;
  count: number;
  editable: boolean;
  onDelete: () => void;
  onMove: (direction: -1 | 1) => void;
}) {
  return (
    <li className="flex items-start justify-between gap-3 rounded-lg border border-buddy-border px-4 py-3">
      <div>
        <div className="flex items-center gap-2">
          <span className="font-medium text-foreground">{task.title}</span>
          <Badge tone="info">{task.task_type}</Badge>
          {!task.required && <Badge tone="neutral">optional</Badge>}
        </div>
        {task.description && (
          <p className="mt-1 text-xs text-buddy-muted">{task.description}</p>
        )}
      </div>
      {editable && (
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            aria-label="Move up"
            disabled={index === 0}
            onClick={() => onMove(-1)}
            className="rounded px-2 py-1 text-xs text-buddy-muted hover:text-foreground disabled:opacity-30"
          >
            ↑
          </button>
          <button
            type="button"
            aria-label="Move down"
            disabled={index === count - 1}
            onClick={() => onMove(1)}
            className="rounded px-2 py-1 text-xs text-buddy-muted hover:text-foreground disabled:opacity-30"
          >
            ↓
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="rounded px-2 py-1 text-xs text-red-600 dark:text-red-400 hover:underline"
          >
            Delete
          </button>
        </div>
      )}
    </li>
  );
}

// ---- Evidence ----

function EvidencePanel({
  quest,
  editable,
  onChanged,
}: {
  quest: QuestDetail;
  editable: boolean;
  onChanged: () => void;
}) {
  const hint = getQuestTypeHint(quest.quest_type);
  const evidence = quest.evidence.slice().sort((a, b) => a.sort_order - b.sort_order);
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [evidenceType, setEvidenceType] = useState<QuestEvidenceType>("TEXT");
  const [contentText, setContentText] = useState("{}");
  const [error, setError] = useState<string | null>(null);

  const resetForm = () => {
    setTitle("");
    setDescription("");
    setEvidenceType("TEXT");
    setContentText("{}");
    setAdding(false);
  };

  const handleAdd = async () => {
    if (!title.trim()) {
      setError("Give this evidence item a title.");
      return;
    }
    let content: Record<string, unknown>;
    try {
      content = JSON.parse(contentText || "{}") as Record<string, unknown>;
    } catch {
      setError("Content must be valid JSON, e.g. {\"summary\": \"...\"}");
      return;
    }
    setError(null);
    try {
      await createQuestEvidence(quest.id, {
        title: title.trim(),
        description: description.trim() || null,
        evidence_type: evidenceType,
        content,
        sort_order: evidence.length,
      });
      resetForm();
      onChanged();
    } catch {
      setError("Couldn't add this evidence item.");
    }
  };

  const handleDelete = async (evidenceId: string) => {
    try {
      await deleteQuestEvidence(quest.id, evidenceId);
      onChanged();
    } catch {
      setError("Couldn't remove this evidence item.");
    }
  };

  const move = async (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= evidence.length) return;
    const a = evidence[index];
    const b = evidence[target];
    try {
      await Promise.all([
        updateQuestEvidence(quest.id, a.id, { sort_order: b.sort_order }),
        updateQuestEvidence(quest.id, b.id, { sort_order: a.sort_order }),
      ]);
      onChanged();
    } catch {
      setError("Couldn't reorder evidence.");
    }
  };

  return (
    <Card className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
              Evidence
            </p>
            <Badge tone={hint.evidenceRequired ? "warning" : "neutral"}>
              {hint.evidenceRequired ? "required" : "optional"}
            </Badge>
          </div>
          <p className="mt-1 text-sm text-buddy-muted">
            The material an employee investigates — metrics, logs, documents, whatever the
            challenge needs.
          </p>
          <p className="mt-1 text-xs text-buddy-primary">{hint.evidenceHint}</p>
        </div>
        {editable && !adding && (
          <Button variant="secondary" onClick={() => setAdding(true)}>
            + Add evidence
          </Button>
        )}
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      <ul className="space-y-2">
        {evidence.map((item, i) => (
          <EvidenceRow
            key={item.id}
            item={item}
            index={i}
            count={evidence.length}
            editable={editable}
            onDelete={() => handleDelete(item.id)}
            onMove={(dir) => move(i, dir)}
          />
        ))}
        {evidence.length === 0 && !adding && (
          <li className="text-sm text-buddy-muted">No evidence yet.</li>
        )}
      </ul>

      {adding && (
        <div className="space-y-3 rounded-lg border border-buddy-border p-4">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Evidence title"
            className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
          />
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description (optional)"
            rows={2}
            className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
          />
          <select
            value={evidenceType}
            onChange={(e) => setEvidenceType(e.target.value as QuestEvidenceType)}
            className="rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
          >
            {EVIDENCE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <div>
            <label
              htmlFor="ev-content"
              className="mb-1 block text-xs font-medium text-buddy-muted"
            >
              Content (JSON — whatever fields fit this evidence type)
            </label>
            <textarea
              id="ev-content"
              value={contentText}
              onChange={(e) => setContentText(e.target.value)}
              rows={4}
              className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 font-mono text-xs"
            />
          </div>
          <div className="flex gap-2">
            <Button onClick={handleAdd}>Add evidence</Button>
            <Button variant="ghost" onClick={resetForm}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

function EvidenceRow({
  item,
  index,
  count,
  editable,
  onDelete,
  onMove,
}: {
  item: QuestEvidenceItem;
  index: number;
  count: number;
  editable: boolean;
  onDelete: () => void;
  onMove: (direction: -1 | 1) => void;
}) {
  return (
    <li className="flex items-start justify-between gap-3 rounded-lg border border-buddy-border px-4 py-3">
      <div>
        <div className="flex items-center gap-2">
          <span className="font-medium text-foreground">{item.title}</span>
          <Badge tone="info">{item.evidence_type}</Badge>
        </div>
        {item.description && (
          <p className="mt-1 text-xs text-buddy-muted">{item.description}</p>
        )}
      </div>
      {editable && (
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            aria-label="Move up"
            disabled={index === 0}
            onClick={() => onMove(-1)}
            className="rounded px-2 py-1 text-xs text-buddy-muted hover:text-foreground disabled:opacity-30"
          >
            ↑
          </button>
          <button
            type="button"
            aria-label="Move down"
            disabled={index === count - 1}
            onClick={() => onMove(1)}
            className="rounded px-2 py-1 text-xs text-buddy-muted hover:text-foreground disabled:opacity-30"
          >
            ↓
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="rounded px-2 py-1 text-xs text-red-600 dark:text-red-400 hover:underline"
          >
            Delete
          </button>
        </div>
      )}
    </li>
  );
}

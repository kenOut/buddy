"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { createQuestCriterion, deleteQuestCriterion } from "@/lib/admin-quests";
import type { QuestCriterionType, QuestDetail, QuestEvaluationCriterion } from "@/lib/types";
import { getQuestTypeHint } from "@/lib/questTypeHints";

const CRITERION_TYPES: QuestCriterionType[] = ["DETERMINISTIC", "BEHAVIORAL", "QUALITATIVE"];

const CRITERION_HELP: Record<QuestCriterionType, string> = {
  DETERMINISTIC:
    "There's one objectively correct answer (e.g. a specific service name or root cause). Set an expected answer below.",
  BEHAVIORAL:
    "Judges what the employee did, not a single right answer (e.g. did they check logs before guessing?). Describe the expected behavior.",
  QUALITATIVE:
    "Judges the quality of reasoning or communication holistically. A reference solution can guide the AI reviewer, but there's no single correct string.",
};

export function EvaluationSection({
  quest,
  editable,
  onChanged,
}: {
  quest: QuestDetail;
  editable: boolean;
  onChanged: () => void;
}) {
  const hint = getQuestTypeHint(quest.quest_type);
  const criteria = quest.evaluation_criteria.slice().sort((a, b) => a.sort_order - b.sort_order);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [criterionType, setCriterionType] = useState<QuestCriterionType>("QUALITATIVE");
  const [expectedAnswer, setExpectedAnswer] = useState("");
  const [expectedBehavior, setExpectedBehavior] = useState("");
  const [referenceSolution, setReferenceSolution] = useState("");
  const [maxScore, setMaxScore] = useState(100);
  const [error, setError] = useState<string | null>(null);

  const resetForm = () => {
    setName("");
    setDescription("");
    setCriterionType("QUALITATIVE");
    setExpectedAnswer("");
    setExpectedBehavior("");
    setReferenceSolution("");
    setMaxScore(100);
    setAdding(false);
  };

  const handleAdd = async () => {
    if (!name.trim()) {
      setError("Give this criterion a name.");
      return;
    }
    setError(null);
    try {
      await createQuestCriterion(quest.id, {
        name: name.trim(),
        description: description.trim() || null,
        criterion_type: criterionType,
        expected_answer: expectedAnswer.trim() || null,
        expected_behavior: expectedBehavior.trim() || null,
        reference_solution: referenceSolution.trim() || null,
        max_score: maxScore,
        sort_order: criteria.length,
      });
      resetForm();
      onChanged();
    } catch {
      setError("Couldn't add this criterion.");
    }
  };

  const handleDelete = async (criterionId: string) => {
    try {
      await deleteQuestCriterion(quest.id, criterionId);
      onChanged();
    } catch {
      setError("Couldn't remove this criterion.");
    }
  };

  return (
    <Card className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
            Evaluation criteria
          </p>
          <p className="mt-1 text-sm text-buddy-muted">
            🔒 Evaluator-only. Everything here — expected answers, expected behavior, reference
            solutions — is used by Buddy&rsquo;s AI reviewer and is <strong>never shown to the
            employee</strong>, before or after they submit. Add at least two.
          </p>
          <p className="mt-1 text-xs text-buddy-primary">{hint.evaluationHint}</p>
        </div>
        {editable && !adding && (
          <Button variant="secondary" onClick={() => setAdding(true)}>
            + Add criterion
          </Button>
        )}
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      <ul className="space-y-2">
        {criteria.map((criterion) => (
          <CriterionRow
            key={criterion.id}
            criterion={criterion}
            editable={editable}
            onDelete={() => handleDelete(criterion.id)}
          />
        ))}
        {criteria.length === 0 && !adding && (
          <li className="text-sm text-buddy-muted">No evaluation criteria yet.</li>
        )}
      </ul>

      {adding && (
        <div className="space-y-3 rounded-lg border border-buddy-border p-4">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Criterion name, e.g. Identifies the root cause"
            className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
          />
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description (optional, employee-invisible)"
            rows={2}
            className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
          />
          <div>
            <select
              value={criterionType}
              onChange={(e) => setCriterionType(e.target.value as QuestCriterionType)}
              className="rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
            >
              {CRITERION_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-buddy-muted">{CRITERION_HELP[criterionType]}</p>
          </div>

          <div className="rounded-lg border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40 p-3 space-y-3">
            <p className="text-xs font-semibold text-amber-900 dark:text-amber-200">
              🔒 Evaluator-only — hidden from every employee view
            </p>
            {criterionType === "DETERMINISTIC" && (
              <input
                value={expectedAnswer}
                onChange={(e) => setExpectedAnswer(e.target.value)}
                placeholder="Expected answer"
                className="w-full rounded-lg border border-buddy-border bg-white px-3 py-2 text-sm"
              />
            )}
            {criterionType === "BEHAVIORAL" && (
              <textarea
                value={expectedBehavior}
                onChange={(e) => setExpectedBehavior(e.target.value)}
                placeholder="Expected behavior"
                rows={2}
                className="w-full rounded-lg border border-buddy-border bg-white px-3 py-2 text-sm"
              />
            )}
            {criterionType === "QUALITATIVE" && (
              <textarea
                value={referenceSolution}
                onChange={(e) => setReferenceSolution(e.target.value)}
                placeholder="Reference solution (optional guidance for the AI reviewer)"
                rows={2}
                className="w-full rounded-lg border border-buddy-border bg-white px-3 py-2 text-sm"
              />
            )}
          </div>

          <div>
            <label htmlFor="ec-score" className="mb-1 block text-xs font-medium text-buddy-muted">
              Max score
            </label>
            <input
              id="ec-score"
              type="number"
              min={1}
              value={maxScore}
              onChange={(e) => setMaxScore(Number(e.target.value))}
              className="w-32 rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
            />
          </div>

          <div className="flex gap-2">
            <Button onClick={handleAdd}>Add criterion</Button>
            <Button variant="ghost" onClick={resetForm}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

function CriterionRow({
  criterion,
  editable,
  onDelete,
}: {
  criterion: QuestEvaluationCriterion;
  editable: boolean;
  onDelete: () => void;
}) {
  const hiddenValue =
    criterion.expected_answer || criterion.expected_behavior || criterion.reference_solution;

  return (
    <li className="space-y-2 rounded-lg border border-buddy-border px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-medium text-foreground">{criterion.name}</span>
            <Badge tone="info">{criterion.criterion_type}</Badge>
          </div>
          {criterion.description && (
            <p className="mt-1 text-xs text-buddy-muted">{criterion.description}</p>
          )}
        </div>
        {editable && (
          <button
            type="button"
            onClick={onDelete}
            className="shrink-0 rounded px-2 py-1 text-xs text-red-600 dark:text-red-400 hover:underline"
          >
            Delete
          </button>
        )}
      </div>
      {hiddenValue && (
        <div className="rounded-lg bg-amber-50 dark:bg-amber-950/40 px-3 py-2 text-xs text-amber-900 dark:text-amber-200">
          🔒 Evaluator-only: {hiddenValue}
        </div>
      )}
      <p className="text-xs text-buddy-muted">Max score: {criterion.max_score}</p>
    </li>
  );
}

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { Card } from "@/components/ui/Card";
import { QuestChallenge } from "@/components/quests/QuestChallenge";
import { QuestEvidencePanel } from "@/components/quests/QuestEvidencePanel";
import { QuestHeader } from "@/components/quests/QuestHeader";
import { getQuestDetail } from "@/lib/admin-quests";
import type { EmployeeQuest } from "@/lib/types";

/**
 * Manager-only, read-only render of what an employee would see. Fetches
 * the manager QuestDetail (so a DRAFT quest can be previewed before
 * publishing) but only ever passes the employee-safe subset — title,
 * description, quest_type, workspace_type, difficulty, tasks, evidence —
 * into the same presentational components the real employee Quest
 * Workspace uses. Deliberately does NOT call createQuestAttempt,
 * getEmployeeQuest, or getQuestEligibility: no QuestAttempt, evidence, or
 * evaluation is ever created by visiting this page (Stage 6A §29).
 */
export default function QuestPreviewPage() {
  const params = useParams<{ questId: string }>();
  const questId = params.questId;

  const [quest, setQuest] = useState<EmployeeQuest | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getQuestDetail(questId)
      .then((detail) => {
        if (cancelled) return;
        setQuest({
          id: detail.id,
          title: detail.title,
          description: detail.description,
          quest_type: detail.quest_type,
          workspace_type: detail.workspace_type,
          difficulty: detail.difficulty,
          tasks: detail.tasks,
          evidence: detail.evidence,
          // This is a manager preview, not tied to any real employee
          // assignment — there is no real readiness context to reflect,
          // so this stays false rather than fabricating a claim.
          required_for_readiness: false,
        });
      })
      .catch(() => {
        if (!cancelled) setError("Couldn't load this Quest.");
      });
    return () => {
      cancelled = true;
    };
  }, [questId]);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <Link
        href={`/admin/quests/${questId}`}
        className="text-sm text-buddy-muted hover:text-foreground"
      >
        ← Back to Builder
      </Link>

      <Card className="border-buddy-primary/30 bg-buddy-primary/5">
        <p className="text-sm text-buddy-primary-dark">
          <strong>Manager preview.</strong> This is exactly what an eligible employee would see —
          read only. No attempt, evidence, or evaluation is created by viewing this page.
        </p>
      </Card>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      {!quest && !error && <p className="text-sm text-buddy-muted">Loading preview…</p>}

      {quest && (
        <>
          <QuestHeader quest={quest} />
          <QuestChallenge quest={quest} />
          {quest.evidence.length > 0 && (
            <Card>
              <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-buddy-primary">
                Evidence
              </p>
              <QuestEvidencePanel evidence={quest.evidence} />
            </Card>
          )}
        </>
      )}
    </div>
  );
}

"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { AssignPublishSection } from "@/components/admin/quest-builder/AssignPublishSection";
import { BasicInfoSection } from "@/components/admin/quest-builder/BasicInfoSection";
import { BuilderNav, type BuilderSectionKey } from "@/components/admin/quest-builder/BuilderNav";
import { CapabilitiesSection } from "@/components/admin/quest-builder/CapabilitiesSection";
import { ChallengeSection } from "@/components/admin/quest-builder/ChallengeSection";
import { EvaluationSection } from "@/components/admin/quest-builder/EvaluationSection";
import { WorkEvidenceSection } from "@/components/admin/quest-builder/WorkEvidenceSection";
import { getPublishReadiness, getQuestDetail } from "@/lib/admin-quests";
import type { QuestDetail, QuestQualityValidation, QuestStatus } from "@/lib/types";

const STATUS_TONE: Record<QuestStatus, "neutral" | "success" | "warning"> = {
  DRAFT: "warning",
  PUBLISHED: "success",
  ARCHIVED: "neutral",
};

export default function QuestBuilderPage() {
  const params = useParams<{ questId: string }>();
  const questId = params.questId;

  const [quest, setQuest] = useState<QuestDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [section, setSection] = useState<BuilderSectionKey>("basic-info");
  const [quality, setQuality] = useState<QuestQualityValidation | null>(null);

  const reload = useCallback(() => {
    return getQuestDetail(questId)
      .then((q) => {
        setQuest(q);
        setLoadError(null);
        if (q.status === "DRAFT") {
          getPublishReadiness(questId).then(setQuality);
        }
      })
      .catch(() => setLoadError("Couldn't load this Quest."));
  }, [questId]);

  useEffect(() => {
    reload();
  }, [reload]);

  if (loadError) {
    return (
      <div className="space-y-4">
        <p role="alert" className="text-sm text-red-600">
          {loadError}
        </p>
        <Link href="/admin/quests" className="text-sm text-buddy-primary hover:underline">
          ← Back to Quests
        </Link>
      </div>
    );
  }

  if (!quest) {
    return <p className="text-sm text-buddy-muted">Loading Quest…</p>;
  }

  const editable = quest.status === "DRAFT";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link href="/admin/quests" className="text-xs text-buddy-muted hover:text-foreground">
            ← Quests
          </Link>
          <div className="mt-1 flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold">{quest.title || "Untitled Quest"}</h1>
            <Badge tone={STATUS_TONE[quest.status]}>{quest.status}</Badge>
            {editable && quality && (
              <button
                type="button"
                onClick={() => setSection("assign-publish")}
                className="text-sm hover:underline"
              >
                {quality.ready ? (
                  <span className="text-emerald-700">✓ Ready to publish</span>
                ) : (
                  <span className="text-amber-700">
                    ✕ {quality.errors.length} issue{quality.errors.length === 1 ? "" : "s"} to fix
                  </span>
                )}
              </button>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <Link
            href={`/admin/quests/${questId}/preview`}
            className="rounded-full border border-buddy-border px-4 py-2 text-sm font-medium text-foreground hover:border-buddy-primary/50"
          >
            Preview
          </Link>
        </div>
      </div>

      {!editable && (
        <Card className="border-amber-300 bg-amber-50 text-amber-900">
          <p className="text-sm">
            This Quest is <strong>{quest.status.toLowerCase()}</strong> — its challenge, tasks,
            evidence, evaluation criteria, and capability mappings are read-only. Who it&rsquo;s
            assigned to can still be changed in Assign &amp; Publish.
          </p>
        </Card>
      )}

      <BuilderNav current={section} onChange={setSection} />

      <div>
        {section === "basic-info" && (
          <BasicInfoSection quest={quest} editable={editable} onSaved={reload} />
        )}
        {section === "challenge" && (
          <ChallengeSection quest={quest} editable={editable} onSaved={reload} />
        )}
        {section === "work-evidence" && (
          <WorkEvidenceSection quest={quest} editable={editable} onChanged={reload} />
        )}
        {section === "evaluation" && (
          <EvaluationSection quest={quest} editable={editable} onChanged={reload} />
        )}
        {section === "capabilities" && (
          <CapabilitiesSection quest={quest} editable={editable} onChanged={reload} />
        )}
        {section === "assign-publish" && (
          <AssignPublishSection quest={quest} onChanged={reload} onNavigateToSection={setSection} />
        )}
      </div>
    </div>
  );
}

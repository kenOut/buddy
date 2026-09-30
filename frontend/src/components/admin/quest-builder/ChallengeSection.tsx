"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { updateQuest } from "@/lib/admin-quests";
import type { QuestDetail } from "@/lib/types";
import { SaveStateIndicator, type BuilderSaveState } from "./SaveStateIndicator";

export function ChallengeSection({
  quest,
  editable,
  onSaved,
}: {
  quest: QuestDetail;
  editable: boolean;
  onSaved: () => void;
}) {
  const [description, setDescription] = useState(quest.description ?? "");
  const [saveState, setSaveState] = useState<BuilderSaveState>("idle");

  useEffect(() => {
    // Pulls in fresh data after a reload (e.g. following a save) —
    // synchronous, since there's nothing async to defer this into.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDescription(quest.description ?? "");
  }, [quest]);

  const handleSave = async () => {
    setSaveState("saving");
    try {
      await updateQuest(quest.id, { description });
      setSaveState("saved");
      onSaved();
    } catch {
      setSaveState("error");
    }
  };

  return (
    <Card className="space-y-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
          The challenge
        </p>
        <p className="mt-1 text-sm text-buddy-muted">
          Describe the real-work problem the employee is being asked to solve, and what a good
          outcome looks like. This is the only thing an employee sees before they start — write
          it the way you&rsquo;d brief a real teammate, not a quiz prompt.
        </p>
      </div>

      <textarea
        value={description}
        disabled={!editable}
        onChange={(e) => setDescription(e.target.value)}
        rows={10}
        placeholder="e.g. Checkout latency has spiked 3x in the EU region over the last 48 hours. Investigate the likely cause using the provided metrics and logs, and propose a fix. A good outcome names the specific service responsible and a concrete next step."
        className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm disabled:opacity-60"
      />

      {!description.trim() && (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          A Quest can&rsquo;t be published without a challenge description.
        </p>
      )}

      {editable && (
        <div className="flex items-center gap-3">
          <Button onClick={handleSave} disabled={saveState === "saving"}>
            Save
          </Button>
          <SaveStateIndicator state={saveState} onRetry={handleSave} />
        </div>
      )}
    </Card>
  );
}

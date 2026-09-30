"use client";

import { useEffect, useState } from "react";

import { Card } from "@/components/ui/Card";
import { mapQuestCapability, unmapQuestCapability } from "@/lib/admin-quests";
import { api } from "@/lib/api";
import type { Capability, QuestDetail } from "@/lib/types";

export function CapabilitiesSection({
  quest,
  editable,
  onChanged,
}: {
  quest: QuestDetail;
  editable: boolean;
  onChanged: () => void;
}) {
  const [allCapabilities, setAllCapabilities] = useState<Capability[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    api.get<Capability[]>("/capabilities").then(setAllCapabilities);
  }, []);

  const mappedIds = new Set(quest.capabilities.map((c) => c.capability_id));

  const handleToggle = async (capability: Capability) => {
    setError(null);
    setBusyId(capability.id);
    try {
      if (mappedIds.has(capability.id)) {
        await unmapQuestCapability(quest.id, capability.id);
      } else {
        await mapQuestCapability(quest.id, { capability_id: capability.id });
      }
      onChanged();
    } catch {
      setError("Couldn't update this capability mapping.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Card className="space-y-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
          Capabilities
        </p>
        <p className="mt-1 text-sm text-buddy-muted">
          What does completing this Quest tell us about the employee? Map at least one
          capability — Buddy uses these mappings to turn a completed Quest into real capability
          evidence on the employee&rsquo;s profile. A Quest cannot be published without at least
          one capability mapped.
        </p>
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      {quest.capabilities.length === 0 && (
        <p className="text-xs text-amber-700 dark:text-amber-400">No capabilities mapped yet.</p>
      )}

      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {allCapabilities.map((capability) => {
          const mapped = mappedIds.has(capability.id);
          return (
            <li key={capability.id}>
              <label
                className={`flex cursor-pointer items-start gap-3 rounded-lg border px-4 py-3 text-sm transition-colors ${
                  mapped
                    ? "border-buddy-primary bg-buddy-primary/5"
                    : "border-buddy-border"
                } ${!editable ? "cursor-default opacity-70" : ""}`}
              >
                <input
                  type="checkbox"
                  checked={mapped}
                  disabled={!editable || busyId === capability.id}
                  onChange={() => handleToggle(capability)}
                  className="mt-0.5"
                />
                <span>
                  <span className="block font-medium text-foreground">{capability.name}</span>
                  {capability.description && (
                    <span className="block text-xs text-buddy-muted">
                      {capability.description}
                    </span>
                  )}
                </span>
              </label>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

"use client";

import { useState } from "react";

import { Card } from "@/components/ui/Card";
import type { CapabilityAnalyticsSummary, CapabilityGapCategory, CapabilityLevel } from "@/lib/types";
import { CapabilityEmployeesModal } from "./CapabilityEmployeesModal";

const LEVEL_COLOR: Record<CapabilityLevel, string> = {
  NOT_OBSERVED: "bg-buddy-border",
  DEVELOPING: "bg-buddy-sunrise",
  CAPABLE: "bg-buddy-primary/60",
  STRONG: "bg-buddy-aurora",
};

const LEVEL_TO_CATEGORY: Record<CapabilityLevel, CapabilityGapCategory> = {
  NOT_OBSERVED: "UNOBSERVED",
  DEVELOPING: "DEVELOPMENT_AREA",
  CAPABLE: "CAPABLE",
  STRONG: "STRENGTH",
};

/**
 * Phase 6E Part 8-9, 15 — evidence-backed aggregate patterns only.
 * Categories with zero employees in them are never shown (Part 8: "only
 * display categories that are actually represented"). Clicking any
 * segment or the "quests producing evidence" list opens the Part 11
 * drill-down.
 */
export function CapabilityDevelopmentSection({
  capabilities,
  departmentId,
}: {
  capabilities: CapabilityAnalyticsSummary[];
  departmentId: string | null;
}) {
  const [drilldown, setDrilldown] = useState<{
    capabilityId: string;
    capabilityName: string;
    category: CapabilityGapCategory;
  } | null>(null);

  const anyObserved = capabilities.some((c) => c.observed_employees > 0);

  return (
    <>
      {!anyObserved ? (
        <Card>
          <p className="text-sm text-buddy-muted">
            Capability evidence will appear after employees complete evaluated work.
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {capabilities.map((capability) => (
            <Card key={capability.capability_id}>
              <p className="text-sm font-semibold text-buddy-navy">{capability.capability_name}</p>
              <p className="mt-1 text-xs text-buddy-muted">
                {capability.observed_employees} of {capability.total_employees} employees observed
              </p>

              {capability.level_breakdown.length > 0 && (
                <div className="mt-3 space-y-1.5">
                  {capability.level_breakdown.map((b) => (
                    <button
                      key={b.level}
                      type="button"
                      onClick={() =>
                        setDrilldown({
                          capabilityId: capability.capability_id,
                          capabilityName: capability.capability_name,
                          category: LEVEL_TO_CATEGORY[b.level],
                        })
                      }
                      className="flex w-full items-center gap-2 text-left text-xs hover:opacity-80"
                    >
                      <span className={`h-2 w-2 shrink-0 rounded-full ${LEVEL_COLOR[b.level]}`} />
                      <span className="w-20 shrink-0 text-buddy-muted">{b.level.toLowerCase()}</span>
                      <span className="font-medium text-buddy-text-primary underline decoration-dotted">
                        {b.employee_count}
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {capability.quests_producing_evidence.length > 0 && (
                <div className="mt-4 border-t border-buddy-border pt-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">
                    Evidence observed through
                  </p>
                  <ul className="mt-1.5 space-y-1 text-xs text-buddy-text-secondary">
                    {capability.quests_producing_evidence.map((q) => (
                      <li key={q.quest_id}>
                        {q.quest_title} ({q.evidence_count})
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}

      {drilldown && (
        <CapabilityEmployeesModal
          capabilityId={drilldown.capabilityId}
          capabilityName={drilldown.capabilityName}
          category={drilldown.category}
          departmentId={departmentId}
          onClose={() => setDrilldown(null)}
        />
      )}
    </>
  );
}

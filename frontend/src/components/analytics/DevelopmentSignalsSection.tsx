"use client";

import { useState } from "react";

import { Card } from "@/components/ui/Card";
import type { DevelopmentSignalItem } from "@/lib/types";
import { CapabilityEmployeesModal } from "./CapabilityEmployeesModal";

/**
 * Phase 6E Part 9 — "N employees currently have capability X classified
 * as a development area." Never "X is the team's biggest weakness" —
 * just a count, sorted descending, each one clickable into the Part 11
 * employee drill-down.
 */
export function DevelopmentSignalsSection({
  signals,
  departmentId,
}: {
  signals: DevelopmentSignalItem[];
  departmentId: string | null;
}) {
  const [drilldown, setDrilldown] = useState<{ capabilityId: string; capabilityName: string } | null>(
    null
  );

  if (signals.length === 0) {
    return (
      <Card>
        <p className="text-sm text-buddy-muted">
          No development recommendations have been generated yet.
        </p>
      </Card>
    );
  }

  const max = Math.max(...signals.map((s) => s.employee_count));

  return (
    <>
      <Card className="space-y-3">
        <p className="text-xs text-buddy-muted">
          Number of employees whose current profile classifies this capability as a development
          area.
        </p>
        <ul className="space-y-2">
          {signals.map((signal) => (
            <li key={signal.capability_id}>
              <button
                type="button"
                onClick={() =>
                  setDrilldown({ capabilityId: signal.capability_id, capabilityName: signal.capability_name })
                }
                className="flex w-full items-center gap-3 text-left hover:opacity-80"
              >
                <span className="w-36 shrink-0 truncate text-sm text-buddy-text-primary">
                  {signal.capability_name}
                </span>
                <div className="h-4 flex-1 overflow-hidden rounded-full bg-buddy-border/40">
                  <div
                    className="h-full rounded-full bg-buddy-sunrise"
                    style={{ width: `${(signal.employee_count / max) * 100}%` }}
                  />
                </div>
                <span className="w-28 shrink-0 text-right text-xs text-buddy-muted underline decoration-dotted">
                  {signal.employee_count} employee{signal.employee_count === 1 ? "" : "s"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </Card>

      {drilldown && (
        <CapabilityEmployeesModal
          capabilityId={drilldown.capabilityId}
          capabilityName={drilldown.capabilityName}
          category="DEVELOPMENT_AREA"
          departmentId={departmentId}
          onClose={() => setDrilldown(null)}
        />
      )}
    </>
  );
}

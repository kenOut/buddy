"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { getCapabilityEmployees } from "@/lib/analytics";
import type { CapabilityEmployeesResponse, CapabilityGapCategory } from "@/lib/types";

const CATEGORY_LABEL: Record<CapabilityGapCategory, string> = {
  STRENGTH: "classified as a strength",
  CAPABLE: "classified as capable",
  DEVELOPMENT_AREA: "classified as a development area",
  UNOBSERVED: "not yet observed",
};

/**
 * Phase 6E Part 11 — the drill-down behind an aggregate count ("6
 * employees have Documentation classified as a development area").
 * Shows who, without exposing anything beyond what /analytics already
 * returns — no evaluation criteria, no scores, just names/roles/
 * departments/levels/evidence counts, plus a link into the existing
 * employee detail page for further context.
 */
export function CapabilityEmployeesModal({
  capabilityId,
  capabilityName,
  category,
  departmentId,
  onClose,
}: {
  capabilityId: string;
  capabilityName: string;
  category: CapabilityGapCategory;
  departmentId: string | null;
  onClose: () => void;
}) {
  const [data, setData] = useState<CapabilityEmployeesResponse | null>(null);

  useEffect(() => {
    getCapabilityEmployees(capabilityId, category, departmentId).then(setData);
  }, [capabilityId, category, departmentId]);

  return (
    <div
      className="fixed inset-0 z-20 flex items-start justify-center overflow-y-auto bg-black/30 px-4 py-10"
      onClick={onClose}
    >
      <div className="w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
        <Card>
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">
                {capabilityName}
              </p>
              <p className="mt-1 text-sm text-buddy-muted">
                Employees currently {CATEGORY_LABEL[category]}.
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="text-buddy-muted hover:text-foreground"
            >
              ✕
            </button>
          </div>

          <div className="mt-4">
            {!data && <p className="text-sm text-buddy-muted">Loading…</p>}
            {data && data.employees.length === 0 && (
              <p className="text-sm text-buddy-muted">No employees match this right now.</p>
            )}
            {data && data.employees.length > 0 && (
              <ul className="space-y-2">
                {data.employees.map((employee) => (
                  <li
                    key={employee.employee_id}
                    className="flex items-center justify-between rounded-lg border border-buddy-border px-4 py-2 text-sm"
                  >
                    <div>
                      <Link
                        href={`/admin/employees/${employee.employee_id}`}
                        className="font-medium text-foreground hover:text-buddy-primary"
                      >
                        {employee.full_name}
                      </Link>
                      <p className="text-xs text-buddy-muted">
                        {employee.role_title ?? "—"} · {employee.department_name ?? "No department"}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge tone="neutral">{employee.evidence_count} evidence</Badge>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

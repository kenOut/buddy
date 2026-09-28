"use client";

import { useEffect, useState } from "react";

import { NewMissionModal } from "@/components/admin/NewMissionModal";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { api } from "@/lib/api";
import type { Department, Mission } from "@/lib/types";

export default function MissionsPage() {
  const [missions, setMissions] = useState<Mission[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [showNewMission, setShowNewMission] = useState(false);

  useEffect(() => {
    api.get<Mission[]>("/missions").then(setMissions);
    api.get<Department[]>("/departments").then(setDepartments);
  }, []);

  const departmentName = (id: string | null) =>
    departments.find((d) => d.id === id)?.name ?? "—";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Missions</h1>
          <p className="mt-1 text-sm text-buddy-muted">
            Onboarding tasks assigned to new hires by department.
          </p>
        </div>
        <Button disabled={departments.length === 0} onClick={() => setShowNewMission(true)}>
          New mission
        </Button>
      </div>

      {showNewMission && (
        <NewMissionModal
          departments={departments}
          onClose={() => setShowNewMission(false)}
          onCreated={(mission) => setMissions((prev) => [...prev, mission])}
        />
      )}

      <Card className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="border-b border-buddy-border text-xs uppercase tracking-wide text-buddy-muted">
              <tr>
                <th className="px-6 py-3">Mission</th>
                <th className="px-6 py-3">Type</th>
                <th className="px-6 py-3">Work environment</th>
                <th className="px-6 py-3">Department</th>
                <th className="px-6 py-3">Est. time</th>
                <th className="px-6 py-3">Readiness</th>
              </tr>
            </thead>
            <tbody>
              {missions
                .slice()
                .sort((a, b) => a.sort_order - b.sort_order)
                .map((mission) => (
                  <tr key={mission.id} className="border-b border-buddy-border last:border-0">
                    <td className="px-6 py-3">
                      <p className="font-medium text-foreground">{mission.title}</p>
                      {mission.description && (
                        <p className="text-xs text-buddy-muted">{mission.description}</p>
                      )}
                    </td>
                    <td className="px-6 py-3">
                      <Badge tone="info">{mission.mission_type}</Badge>
                    </td>
                    <td className="px-6 py-3">
                      <Badge tone="neutral">{mission.workspace_type}</Badge>
                    </td>
                    <td className="px-6 py-3 text-buddy-muted">
                      {departmentName(mission.department_id)}
                    </td>
                    <td className="px-6 py-3 text-buddy-muted">{mission.estimated_minutes} min</td>
                    <td className="px-6 py-3">
                      {mission.required ? (
                        <Badge tone="coral">Required</Badge>
                      ) : (
                        <span className="text-buddy-muted">Optional</span>
                      )}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

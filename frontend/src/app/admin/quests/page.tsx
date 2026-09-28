"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import {
  archiveQuest,
  getQuestDetail,
  listQuestAssignments,
  listQuests,
  publishQuest,
} from "@/lib/admin-quests";
import { api } from "@/lib/api";
import type { Project, Quest, QuestDetail, QuestDifficulty, QuestStatus, QuestType } from "@/lib/types";

const STATUS_TONE: Record<QuestStatus, "neutral" | "success" | "warning"> = {
  DRAFT: "warning",
  PUBLISHED: "success",
  ARCHIVED: "neutral",
};

const DIFFICULTY_TONE: Record<QuestDifficulty, "neutral" | "info" | "warning" | "coral"> = {
  EASY: "neutral",
  MEDIUM: "info",
  HARD: "warning",
  EXPERT: "coral",
};

interface QuestRow extends Quest {
  taskCount: number;
  evidenceCount: number;
  capabilityCount: number;
  assignmentCount: number;
}

export default function QuestLibraryPage() {
  const router = useRouter();
  const [rows, setRows] = useState<QuestRow[] | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [statusFilter, setStatusFilter] = useState<QuestStatus | "ALL">("ALL");
  const [typeFilter, setTypeFilter] = useState<QuestType | "ALL">("ALL");
  const [projectFilter, setProjectFilter] = useState<string | "ALL">("ALL");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api.get<Project[]>("/projects").then((p) => {
      if (!cancelled) setProjects(p);
    });
    listQuests().then(async (quests) => {
      const withCounts = await Promise.all(
        quests.map(async (quest): Promise<QuestRow> => {
          const [detail, assignments]: [QuestDetail | null, { active: boolean }[]] = await Promise.all([
            getQuestDetail(quest.id).catch(() => null),
            listQuestAssignments(quest.id).catch(() => []),
          ]);
          return {
            ...quest,
            taskCount: detail?.tasks.length ?? 0,
            evidenceCount: detail?.evidence.length ?? 0,
            capabilityCount: detail?.capabilities.length ?? 0,
            assignmentCount: assignments.filter((a) => a.active).length,
          };
        })
      );
      if (!cancelled) setRows(withCounts);
    });
    return () => {
      cancelled = true;
    };
  }, [reloadTick]);

  const projectName = (id: string | null) => projects.find((p) => p.id === id)?.name ?? "—";

  const filtered = useMemo(() => {
    if (!rows) return null;
    return rows.filter((r) => {
      if (statusFilter !== "ALL" && r.status !== statusFilter) return false;
      if (typeFilter !== "ALL" && r.quest_type !== typeFilter) return false;
      if (projectFilter !== "ALL" && r.project_id !== projectFilter) return false;
      return true;
    });
  }, [rows, statusFilter, typeFilter, projectFilter]);

  const handlePublish = async (questId: string) => {
    setBusyId(questId);
    setError(null);
    try {
      await publishQuest(questId);
      setReloadTick((n) => n + 1);
    } catch {
      setError("Couldn't publish this Quest — check its Assign & Publish section for what's missing.");
    } finally {
      setBusyId(null);
    }
  };

  const handleArchive = async (questId: string) => {
    setBusyId(questId);
    setError(null);
    try {
      await archiveQuest(questId);
      setReloadTick((n) => n + 1);
    } catch {
      setError("Couldn't archive this Quest.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Quests</h1>
          <p className="mt-1 text-sm text-buddy-muted">
            Real-work challenges you author and assign to employees.
          </p>
        </div>
        <Button onClick={() => router.push("/admin/quests/new")}>+ New Quest</Button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      <div className="flex flex-wrap gap-3">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as QuestStatus | "ALL")}
          className="rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
        >
          <option value="ALL">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="PUBLISHED">Published</option>
          <option value="ARCHIVED">Archived</option>
        </select>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as QuestType | "ALL")}
          className="rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
        >
          <option value="ALL">All types</option>
          {(
            [
              "INVESTIGATE",
              "TROUBLESHOOT",
              "FIX",
              "BUILD",
              "DESIGN",
              "ANALYZE",
              "CREATE_SOLUTION",
              "OTHER",
            ] as QuestType[]
          ).map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select
          value={projectFilter}
          onChange={(e) => setProjectFilter(e.target.value)}
          className="rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
        >
          <option value="ALL">All projects</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      <Card className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-left text-sm">
            <thead className="border-b border-buddy-border text-xs uppercase tracking-wide text-buddy-muted">
              <tr>
                <th className="px-6 py-3">Quest</th>
                <th className="px-6 py-3">Project</th>
                <th className="px-6 py-3">Type</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3">Difficulty</th>
                <th className="px-6 py-3">Content</th>
                <th className="px-6 py-3">Updated</th>
                <th className="px-6 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered?.map((quest) => (
                <tr key={quest.id} className="border-b border-buddy-border last:border-0">
                  <td className="px-6 py-3">
                    <Link
                      href={`/admin/quests/${quest.id}`}
                      className="font-medium text-foreground hover:text-buddy-primary"
                    >
                      {quest.title}
                    </Link>
                  </td>
                  <td className="px-6 py-3 text-buddy-muted">{projectName(quest.project_id)}</td>
                  <td className="px-6 py-3">
                    <Badge tone="info">{quest.quest_type}</Badge>
                  </td>
                  <td className="px-6 py-3">
                    <Badge tone={STATUS_TONE[quest.status]}>{quest.status}</Badge>
                  </td>
                  <td className="px-6 py-3">
                    <Badge tone={DIFFICULTY_TONE[quest.difficulty]}>
                      {quest.difficulty.toLowerCase()}
                    </Badge>
                  </td>
                  <td className="px-6 py-3 text-xs text-buddy-muted">
                    {quest.taskCount} tasks · {quest.evidenceCount} evidence ·{" "}
                    {quest.capabilityCount} capabilities · {quest.assignmentCount} assigned
                  </td>
                  <td className="px-6 py-3 text-buddy-muted">
                    {new Date(quest.updated_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-3">
                    <div className="flex flex-wrap gap-2">
                      {quest.status === "DRAFT" && (
                        <>
                          <Link
                            href={`/admin/quests/${quest.id}`}
                            className="text-xs font-medium text-buddy-primary hover:underline"
                          >
                            Edit
                          </Link>
                          <Link
                            href={`/admin/quests/${quest.id}/preview`}
                            className="text-xs font-medium text-buddy-primary hover:underline"
                          >
                            Preview
                          </Link>
                          <button
                            type="button"
                            disabled={busyId === quest.id}
                            onClick={() => handlePublish(quest.id)}
                            className="text-xs font-medium text-emerald-700 hover:underline disabled:opacity-50"
                          >
                            Publish
                          </button>
                        </>
                      )}
                      {quest.status === "PUBLISHED" && (
                        <>
                          <Link
                            href={`/admin/quests/${quest.id}`}
                            className="text-xs font-medium text-buddy-primary hover:underline"
                          >
                            View
                          </Link>
                          <Link
                            href={`/admin/quests/${quest.id}/preview`}
                            className="text-xs font-medium text-buddy-primary hover:underline"
                          >
                            Preview
                          </Link>
                          <button
                            type="button"
                            disabled={busyId === quest.id}
                            onClick={() => handleArchive(quest.id)}
                            className="text-xs font-medium text-red-600 hover:underline disabled:opacity-50"
                          >
                            Archive
                          </button>
                        </>
                      )}
                      {quest.status === "ARCHIVED" && (
                        <Link
                          href={`/admin/quests/${quest.id}`}
                          className="text-xs font-medium text-buddy-primary hover:underline"
                        >
                          View
                        </Link>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {filtered && filtered.length === 0 && (
                <tr>
                  <td className="px-6 py-6 text-buddy-muted" colSpan={8}>
                    No Quests match these filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

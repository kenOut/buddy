"use client";

import { useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ApiError, api } from "@/lib/api";
import { WORKSPACE_PROVIDERS, type WorkspaceIntegration } from "@/lib/types";

type LoadState = "loading" | "loaded" | "error";

interface FormValues {
  provider: string;
  display_name: string;
  workspace_link: string;
  external_ref: string;
  active: boolean;
}

function toFormValues(integration: WorkspaceIntegration | null): FormValues {
  return {
    provider: integration?.provider ?? WORKSPACE_PROVIDERS[0],
    display_name: integration?.display_name ?? "",
    workspace_link: integration?.workspace_link ?? "",
    external_ref: integration?.external_ref ?? "",
    active: integration?.active ?? true,
  };
}

export function WorkspaceIntegrationSection({ departmentId }: { departmentId: string }) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [integration, setIntegration] = useState<WorkspaceIntegration | null>(null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<FormValues>(toFormValues(null));
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [toggling, setToggling] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .get<WorkspaceIntegration | null>(`/departments/${departmentId}/workspace`)
      .then((result) => {
        if (cancelled) return;
        setIntegration(result);
        setLoadState("loaded");
      })
      .catch(() => {
        if (cancelled) return;
        setLoadState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [departmentId]);

  function startEditing() {
    setForm(toFormValues(integration));
    setFieldErrors({});
    setFormError(null);
    setEditing(true);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setFieldErrors({});
    setFormError(null);

    const body = {
      provider: form.provider,
      display_name: form.display_name.trim(),
      workspace_link: form.workspace_link.trim(),
      external_ref: form.external_ref.trim(),
      active: form.active,
    };

    try {
      const saved = integration
        ? await api.patch<WorkspaceIntegration>(`/departments/${departmentId}/workspace`, body)
        : await api.post<WorkspaceIntegration>(`/departments/${departmentId}/workspace`, body);
      setIntegration(saved);
      setEditing(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        // FastAPI/Pydantic validation errors — best-effort field mapping.
        try {
          const detail = JSON.parse(err.message) as { detail?: { loc?: (string | number)[]; msg?: string }[] };
          const mapped: Record<string, string> = {};
          for (const item of detail.detail ?? []) {
            const field = item.loc?.[item.loc.length - 1];
            if (typeof field === "string" && item.msg) mapped[field] = item.msg;
          }
          setFieldErrors(mapped);
          if (Object.keys(mapped).length === 0) setFormError("Please check the highlighted fields.");
        } catch {
          setFormError("Please check the highlighted fields.");
        }
      } else if (err instanceof ApiError && err.status === 409) {
        setFormError("This department already has a workspace configured — refresh and try editing it.");
      } else {
        setFormError("Couldn't save the workspace configuration. Try again.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleToggleActive() {
    if (!integration) return;
    setToggling(true);
    try {
      const updated = await api.patch<WorkspaceIntegration>(`/departments/${departmentId}/workspace`, {
        active: !integration.active,
      });
      setIntegration(updated);
    } catch {
      setFormError("Couldn't update the workspace status. Try again.");
    } finally {
      setToggling(false);
    }
  }

  return (
    <Card>
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">Workspace access</p>
        {integration && !editing && (
          <Badge tone={integration.active ? "success" : "neutral"}>
            {integration.active ? "Active" : "Inactive"}
          </Badge>
        )}
      </div>

      {loadState === "loading" && <p className="mt-4 text-sm text-buddy-muted">Loading workspace configuration…</p>}

      {loadState === "error" && (
        <div className="mt-4 space-y-2">
          <p className="text-sm text-buddy-coral">We couldn&rsquo;t check the workspace configuration right now.</p>
          <Button
            variant="secondary"
            onClick={() => {
              setLoadState("loading");
              api
                .get<WorkspaceIntegration | null>(`/departments/${departmentId}/workspace`)
                .then((result) => {
                  setIntegration(result);
                  setLoadState("loaded");
                })
                .catch(() => setLoadState("error"));
            }}
          >
            Try again
          </Button>
        </div>
      )}

      {loadState === "loaded" && !editing && !integration && (
        <div className="mt-4 space-y-3">
          <p className="text-sm text-buddy-muted">No workspace configured for this department.</p>
          <Button onClick={startEditing}>Configure workspace</Button>
        </div>
      )}

      {loadState === "loaded" && !editing && integration && (
        <div className="mt-4 space-y-3 text-sm">
          <div>
            <p className="text-xs uppercase tracking-wide text-buddy-muted">Provider</p>
            <p className="text-foreground">{integration.provider}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-buddy-muted">Workspace name</p>
            <p className="text-foreground">{integration.display_name}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-buddy-muted">Workspace link</p>
            <a
              href={integration.workspace_link}
              target="_blank"
              rel="noopener noreferrer"
              className="break-all text-buddy-primary hover:underline"
            >
              {integration.workspace_link}
            </a>
          </div>
          {formError && <p className="text-buddy-coral">{formError}</p>}
          <div className="flex flex-wrap gap-2 pt-2">
            <Button variant="secondary" onClick={startEditing}>
              Edit
            </Button>
            <Button variant="secondary" onClick={handleToggleActive} disabled={toggling}>
              {toggling ? "Updating…" : integration.active ? "Deactivate" : "Activate"}
            </Button>
          </div>
        </div>
      )}

      {loadState === "loaded" && editing && (
        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="ws-provider" className="text-sm font-medium text-foreground">
              Provider
            </label>
            <select
              id="ws-provider"
              value={form.provider}
              onChange={(e) => setForm((f) => ({ ...f, provider: e.target.value }))}
              className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
            >
              {WORKSPACE_PROVIDERS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            {fieldErrors.provider && <p className="text-xs text-buddy-coral">{fieldErrors.provider}</p>}
          </div>

          <div className="space-y-1.5">
            <label htmlFor="ws-name" className="text-sm font-medium text-foreground">
              Workspace name
            </label>
            <input
              id="ws-name"
              required
              value={form.display_name}
              onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
              placeholder="e.g. Engineering Workspace"
              className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
            />
            {fieldErrors.display_name && (
              <p className="text-xs text-buddy-coral">{fieldErrors.display_name}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <label htmlFor="ws-link" className="text-sm font-medium text-foreground">
              Workspace link
            </label>
            <input
              id="ws-link"
              required
              value={form.workspace_link}
              onChange={(e) => setForm((f) => ({ ...f, workspace_link: e.target.value }))}
              placeholder="https://…"
              className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
            />
            {fieldErrors.workspace_link && (
              <p className="text-xs text-buddy-coral">{fieldErrors.workspace_link}</p>
            )}
          </div>

          <div className="space-y-1.5">
            <label htmlFor="ws-ref" className="text-sm font-medium text-foreground">
              External reference
            </label>
            <input
              id="ws-ref"
              required
              value={form.external_ref}
              onChange={(e) => setForm((f) => ({ ...f, external_ref: e.target.value }))}
              placeholder="e.g. a Shared Drive ID"
              className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm"
            />
            <p className="text-xs text-buddy-muted">
              The provider&rsquo;s own identifier for this workspace — meaningless to employees, used only by
              the configured provider.
            </p>
            {fieldErrors.external_ref && (
              <p className="text-xs text-buddy-coral">{fieldErrors.external_ref}</p>
            )}
          </div>

          <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
            <input
              type="checkbox"
              checked={form.active}
              onChange={(e) => setForm((f) => ({ ...f, active: e.target.checked }))}
            />
            Active
          </label>

          {formError && <p className="text-sm text-buddy-coral">{formError}</p>}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={() => setEditing(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save workspace"}
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}

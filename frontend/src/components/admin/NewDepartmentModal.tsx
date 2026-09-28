"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { api } from "@/lib/api";
import type { Department } from "@/lib/types";

export function NewDepartmentModal({
  organizationId,
  onClose,
  onCreated,
}: {
  organizationId: string;
  onClose: () => void;
  onCreated: (department: Department) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const department = await api.post<Department>("/departments", {
        organization_id: organizationId,
        name: name.trim(),
        description: description.trim() || null,
      });
      onCreated(department);
      onClose();
    } catch {
      setError("Couldn't create the department. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-20 flex items-start justify-center overflow-y-auto bg-black/30 px-4 py-10"
      onClick={onClose}
    >
      <div className="w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <Card>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-foreground">New department</h2>
              <p className="mt-1 text-sm text-buddy-muted">Add a department to the org structure.</p>
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

          <form onSubmit={handleSubmit} className="mt-4 space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="dept-name" className="text-sm font-medium text-foreground">
                Name
              </label>
              <input
                id="dept-name"
                autoFocus
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm focus:border-buddy-primary focus:outline-none"
                placeholder="e.g. Customer Success"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="dept-description" className="text-sm font-medium text-foreground">
                Description <span className="text-buddy-muted">(optional)</span>
              </label>
              <textarea
                id="dept-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm focus:border-buddy-primary focus:outline-none"
              />
            </div>

            {error && <p className="text-sm text-buddy-coral">{error}</p>}

            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="secondary" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" disabled={submitting || !name.trim()}>
                {submitting ? "Creating…" : "Create department"}
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </div>
  );
}

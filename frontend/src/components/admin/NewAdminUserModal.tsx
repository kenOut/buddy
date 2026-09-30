"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { api, ApiError } from "@/lib/api";
import type { AdminUser, AdminUserRole } from "@/lib/types";

const ROLE_LABELS: Record<AdminUserRole, string> = {
  people_culture: "People & Culture",
  security_it: "Security & IT",
  departments: "Departments",
};

export function NewAdminUserModal({
  roles,
  onClose,
  onCreated,
}: {
  roles: AdminUserRole[];
  onClose: () => void;
  onCreated: (user: AdminUser) => void;
}) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<AdminUserRole>(roles[0] ?? "departments");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const user = await api.post<AdminUser>("/admin/users", {
        full_name: fullName.trim(),
        email: email.trim(),
        password,
        role,
      });
      onCreated(user);
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError("An account with this email already exists.");
      } else if (err instanceof ApiError && err.status === 422) {
        setError("Password must be at least 8 characters.");
      } else {
        setError("Couldn't create the account. Try again.");
      }
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
              <h2 className="text-lg font-semibold text-foreground">New user profile</h2>
              <p className="mt-1 text-sm text-buddy-muted">
                Give a stakeholder their own Manager Portal login.
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

          <form onSubmit={handleSubmit} className="mt-4 space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="user-full-name" className="text-sm font-medium text-foreground">
                Full name
              </label>
              <input
                id="user-full-name"
                autoFocus
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm focus:border-buddy-primary focus:outline-none"
                placeholder="e.g. Amara Chukwu"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="user-email" className="text-sm font-medium text-foreground">
                Email
              </label>
              <input
                id="user-email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm focus:border-buddy-primary focus:outline-none"
                placeholder="amara@kowri.com"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="user-password" className="text-sm font-medium text-foreground">
                Temporary password
              </label>
              <input
                id="user-password"
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm focus:border-buddy-primary focus:outline-none"
                placeholder="At least 8 characters"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="user-role" className="text-sm font-medium text-foreground">
                Department
              </label>
              <select
                id="user-role"
                value={role}
                onChange={(e) => setRole(e.target.value as AdminUserRole)}
                className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm focus:border-buddy-primary focus:outline-none"
              >
                {roles.map((r) => (
                  <option key={r} value={r}>
                    {ROLE_LABELS[r] ?? r}
                  </option>
                ))}
              </select>
            </div>

            {error && <p className="text-sm text-buddy-coral">{error}</p>}

            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="secondary" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" disabled={submitting || !fullName.trim() || !email.trim() || password.length < 8}>
                {submitting ? "Creating…" : "Create account"}
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </div>
  );
}

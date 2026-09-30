"use client";

import { useEffect, useState } from "react";

import { NewAdminUserModal } from "@/components/admin/NewAdminUserModal";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { api } from "@/lib/api";
import type { AdminUser, AdminUserRole, Organization } from "@/lib/types";

const ROLE_LABELS: Record<AdminUserRole, string> = {
  people_culture: "People & Culture",
  security_it: "Security & IT",
  departments: "Departments",
};

export default function SettingsPage() {
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [roles, setRoles] = useState<AdminUserRole[]>([]);
  const [showNewUser, setShowNewUser] = useState(false);

  useEffect(() => {
    api.get<Organization[]>("/organizations").then((orgs) => setOrganization(orgs[0] ?? null));
    api.get<AdminUser[]>("/admin/users").then(setUsers);
    api.get<AdminUserRole[]>("/admin/user-roles").then(setRoles);
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="mt-1 text-sm text-buddy-muted">Organization and Manager Portal configuration.</p>
      </div>

      <Card>
        <p className="text-sm font-medium text-foreground">Organization</p>
        {organization ? (
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-buddy-muted">Name</dt>
              <dd className="text-foreground">{organization.name}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-buddy-muted">Slug</dt>
              <dd className="text-foreground">{organization.slug}</dd>
            </div>
          </dl>
        ) : (
          <p className="mt-3 text-sm text-buddy-muted">Loading…</p>
        )}
      </Card>

      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-foreground">User profiles</p>
            <p className="mt-1 text-sm text-buddy-muted">
              Give People &amp; Culture, Security &amp; IT, or department stakeholders their own
              Manager Portal login — same full access as the shared login above.
            </p>
          </div>
          <Button variant="secondary" disabled={roles.length === 0} onClick={() => setShowNewUser(true)}>
            New user profile
          </Button>
        </div>

        {users.length > 0 ? (
          <ul className="mt-4 divide-y divide-buddy-border">
            {users.map((user) => (
              <li key={user.id} className="flex items-center justify-between gap-4 py-3">
                <div>
                  <p className="text-sm font-medium text-foreground">{user.full_name}</p>
                  <p className="text-sm text-buddy-muted">{user.email}</p>
                </div>
                <span className="whitespace-nowrap rounded-full bg-buddy-primary/10 px-3 py-1 text-xs font-medium text-buddy-primary">
                  {ROLE_LABELS[user.role] ?? user.role}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-4 text-sm text-buddy-muted">No user profiles yet.</p>
        )}
      </Card>

      <Card>
        <p className="text-sm font-medium text-foreground">Manager Portal access</p>
        <p className="mt-3 text-sm text-buddy-muted">
          The shared Manager Portal login password and session configuration are set via
          environment variables (<code className="text-xs">ADMIN_PASSWORD</code>,{" "}
          <code className="text-xs">ADMIN_SESSION_SECRET</code>) on the backend, not from this
          page — see the project README for production configuration.
        </p>
      </Card>

      {showNewUser && (
        <NewAdminUserModal
          roles={roles}
          onClose={() => setShowNewUser(false)}
          onCreated={(user) => setUsers((prev) => [...prev, user])}
        />
      )}
    </div>
  );
}

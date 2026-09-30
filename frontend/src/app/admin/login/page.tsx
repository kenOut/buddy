"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { adminLogin } from "@/lib/adminAuth";

export default function AdminLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await adminLogin(password, email.trim() || undefined);
      router.replace("/admin");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-buddy-cloud px-4">
      <ThemeToggle className="fixed right-4 top-4" />
      <Card className="w-full max-w-sm space-y-6">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Buddy Admin</h1>
          <p className="mt-1 text-sm text-buddy-muted">Sign in to access the manager portal.</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="admin-email" className="text-sm font-medium text-foreground">
              Email <span className="font-normal text-buddy-muted">(leave blank for the shared login)</span>
            </label>
            <input
              id="admin-email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm focus:border-buddy-primary focus:outline-none"
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="admin-password" className="text-sm font-medium text-foreground">
              Password
            </label>
            <input
              id="admin-password"
              type="password"
              autoFocus
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm focus:border-buddy-primary focus:outline-none"
            />
          </div>

          {error && <p className="text-sm text-buddy-coral">{error}</p>}

          <Button type="submit" disabled={submitting || !password} className="w-full">
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </Card>
    </div>
  );
}

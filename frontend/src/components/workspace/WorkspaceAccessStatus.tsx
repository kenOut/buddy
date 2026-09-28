"use client";

import { useEffect, useState } from "react";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { BuddySpeech } from "@/components/buddy/BuddySpeech";
import { FadeIn } from "@/components/animations/FadeIn";
import { Button } from "@/components/ui/Button";
import { getWorkspaceAccess } from "@/lib/workspaceAccess";
import type { BuddyState } from "@/components/buddy/buddyStates";
import type { EmployeeWorkspaceAccess } from "@/lib/types";

/** LOADING/API_ERROR have no backend counterpart — everything else is
 * EmployeeWorkspaceAccess["status"] verbatim. Kept as one union so the
 * render switch below is exhaustive and there is exactly one place that
 * decides Buddy's state and copy per status (§14's suggested mapping). */
type ViewState = "LOADING" | "API_ERROR" | EmployeeWorkspaceAccess["status"];

const BUDDY_STATE: Record<ViewState, BuddyState> = {
  LOADING: "thinking",
  GRANTED: "celebrating",
  PENDING: "encouraging",
  FAILED: "encouraging",
  NOT_CONFIGURED: "friendly",
  API_ERROR: "encouraging",
};

export function WorkspaceAccessStatus({ employeeId }: { employeeId: string }) {
  const [view, setView] = useState<ViewState>("LOADING");
  const [access, setAccess] = useState<EmployeeWorkspaceAccess | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getWorkspaceAccess(employeeId)
      .then((result) => {
        if (cancelled) return;
        setAccess(result);
        setView(result.status);
      })
      .catch(() => {
        // A network/server failure here is NOT the same as the backend
        // reporting FAILED — that distinction is the whole point of §12.
        if (cancelled) return;
        setAccess(null);
        setView("API_ERROR");
      });
    return () => {
      cancelled = true;
    };
  }, [employeeId]);

  async function handleRetry() {
    setChecking(true);
    try {
      const result = await getWorkspaceAccess(employeeId);
      setAccess(result);
      setView(result.status);
    } catch {
      setAccess(null);
      setView("API_ERROR");
    } finally {
      setChecking(false);
    }
  }

  const buddyState = BUDDY_STATE[view];

  return (
    <FadeIn duration={0.4} className="w-full">
      <div
        className="flex min-h-[132px] items-start gap-3 rounded-2xl border border-buddy-border bg-buddy-surface p-4 text-left sm:gap-4 sm:p-5"
        role="status"
        aria-live="polite"
      >
        <div className="h-14 w-14 shrink-0 sm:h-16 sm:w-16">
          <BuddyIllustration state={buddyState} label="Buddy" />
        </div>

        <div className="min-w-0 flex-1">
          {view === "LOADING" && (
            <BuddySpeech>
              <p className="text-buddy-text-secondary">Checking your workspace&hellip;</p>
            </BuddySpeech>
          )}

          {view === "GRANTED" && access && (
            <BuddySpeech>
              <p className="font-heading text-lg font-bold text-buddy-navy">
                Your department workspace is ready.
              </p>
              <p className="mt-1 flex items-center gap-1.5 text-sm font-medium text-buddy-primary-dark">
                <span aria-hidden="true">✓</span> Access granted
              </p>
              {access.workspace_link && (
                <a
                  href={access.workspace_link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-4 inline-flex items-center justify-center gap-2 rounded-full bg-buddy-primary px-6 py-3 text-sm font-medium text-white shadow-lg shadow-buddy-primary/25 transition-colors hover:bg-buddy-primary-dark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-buddy-primary focus-visible:ring-offset-2"
                >
                  Enter {access.workspace_name ?? "workspace"}
                  <span aria-hidden="true">↗</span>
                  <span className="sr-only">(opens in a new tab)</span>
                </a>
              )}
            </BuddySpeech>
          )}

          {view === "PENDING" && (
            <BuddySpeech>
              <p className="font-heading text-lg font-bold text-buddy-navy">
                Your department workspace is being prepared.
              </p>
              <p className="mt-1 text-buddy-text-secondary">
                We&rsquo;ll make it available as soon as access is ready.
              </p>
              <button
                type="button"
                onClick={handleRetry}
                disabled={checking}
                className="mt-4 text-sm font-medium text-buddy-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-buddy-primary focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {checking ? "Checking…" : "Check again"}
              </button>
            </BuddySpeech>
          )}

          {view === "FAILED" && (
            <BuddySpeech>
              <p className="font-heading text-lg font-bold text-buddy-navy">
                Your department workspace couldn&rsquo;t be connected yet.
              </p>
              <p className="mt-1 text-buddy-text-secondary">
                Your work is still complete — nothing you&rsquo;ve accomplished has been lost.
              </p>
              <Button
                variant="secondary"
                onClick={handleRetry}
                disabled={checking}
                className="mt-4 focus-visible:ring-2 focus-visible:ring-buddy-primary focus-visible:ring-offset-2"
              >
                {checking ? "Checking…" : "Try Again"}
              </Button>
            </BuddySpeech>
          )}

          {view === "NOT_CONFIGURED" && (
            <BuddySpeech>
              <p className="font-heading text-lg font-bold text-buddy-navy">
                Your department workspace hasn&rsquo;t been connected yet.
              </p>
              <p className="mt-1 text-buddy-text-secondary">
                Your onboarding is complete. Your team can finish the workspace setup separately.
              </p>
            </BuddySpeech>
          )}

          {view === "API_ERROR" && (
            <BuddySpeech>
              <p className="font-heading text-lg font-bold text-buddy-navy">
                We couldn&rsquo;t check your workspace right now.
              </p>
              <p className="mt-1 text-buddy-text-secondary">Your onboarding is still complete.</p>
              <Button
                variant="secondary"
                onClick={handleRetry}
                disabled={checking}
                className="mt-4 focus-visible:ring-2 focus-visible:ring-buddy-primary focus-visible:ring-offset-2"
              >
                {checking ? "Checking…" : "Try Again"}
              </Button>
            </BuddySpeech>
          )}
        </div>
      </div>
    </FadeIn>
  );
}

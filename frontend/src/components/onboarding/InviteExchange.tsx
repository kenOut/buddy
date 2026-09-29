"use client";

import { useEffect, useRef, useState } from "react";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { FadeIn } from "@/components/animations/FadeIn";
import { Card } from "@/components/ui/Card";
import { exchangeInvitation, invitationFailureReason, type InvitationFailureReason } from "@/lib/invitations";

const FAILURE_COPY: Record<InvitationFailureReason, string> = {
  expired: "This invitation has expired. Please request a new invitation.",
  revoked: "This invitation is no longer active.",
  used: "This invitation has already been used.",
  invalid: "This invitation link isn't valid.",
};

type Status = "loading" | "error";

/**
 * P1 — Identity & Invitation Foundation. Exchanges a raw invitation
 * token for an authenticated employee session, then hands off to a real
 * (not client-side) navigation to /onboarding/welcome.
 *
 * That's a hard navigation, not router.push, on purpose: OnboardingProvider
 * (mounted once at the /onboarding layout level, above this page too)
 * already ran its own initial bundle fetch before this exchange set the
 * employee-session cookie, so a client-side route change alone wouldn't
 * pick up the newly authenticated identity — see onboarding-context.tsx's
 * load(), which only runs once per mount. A real navigation remounts the
 * app fresh, this time with the cookie present, and also removes the
 * token from the visible URL and this component's own state in one step
 * (never stored in localStorage/sessionStorage to begin with).
 */
export function InviteExchange({ token }: { token: string }) {
  const [status, setStatus] = useState<Status>("loading");
  const [reason, setReason] = useState<InvitationFailureReason>("invalid");
  // The invitation token is single-use server-side: a second real
  // exchange call with the same token gets rejected as "already used".
  // React 18/19 dev-mode StrictMode deliberately mounts, cleans up, and
  // re-mounts every effect once to surface exactly this kind of
  // not-safe-to-run-twice bug — so the actual network call is deduped
  // through this ref (created at most once per token, shared by both
  // the throwaway first mount and the real second one), while each
  // effect instance still attaches its own `cancelled`-guarded
  // `.then`/`.catch` to whichever promise is live. The throwaway
  // instance's result is discarded by its own cleanup, same as before;
  // the surviving instance's is what actually redirects or shows an
  // error — it's just no longer the one that has to have made the call.
  const exchangePromiseRef = useRef<Promise<void> | null>(null);

  useEffect(() => {
    let cancelled = false;
    exchangePromiseRef.current ??= exchangeInvitation(token);
    exchangePromiseRef.current
      .then(() => {
        if (cancelled) return;
        // Deliberately a hard navigation, not router.push — see the
        // component docstring above for why a client-side route change
        // can't pick up the freshly-set employee-session cookie here.
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.href = "/onboarding/welcome";
      })
      .catch((err) => {
        if (cancelled) return;
        setReason(invitationFailureReason(err));
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-6 py-16 text-center">
      <FadeIn duration={0.6}>
        <div className="mx-auto h-28 w-28">
          <BuddyIllustration state={status === "loading" ? "thinking" : "guide"} label="Buddy" />
        </div>
      </FadeIn>
      <Card className="w-full">
        {status === "loading" ? (
          <p className="text-sm text-buddy-muted">Preparing your Buddy experience…</p>
        ) : (
          <p role="alert" className="text-sm text-buddy-muted">
            {FAILURE_COPY[reason]}
          </p>
        )}
      </Card>
    </div>
  );
}

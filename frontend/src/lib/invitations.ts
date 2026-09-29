import { ApiError, api } from "@/lib/api";

export type InvitationFailureReason = "expired" | "revoked" | "used" | "invalid";

const KNOWN_REASONS: readonly InvitationFailureReason[] = ["expired", "revoked", "used", "invalid"];

/** P1 — Identity & Invitation Foundation. The employee-facing entry
 * point: exchanges a raw invitation token for an authenticated employee
 * session (set server-side as an httpOnly cookie — nothing session-like
 * is ever returned in this response body for the client to store). */
export async function exchangeInvitation(token: string): Promise<void> {
  await api.post("/invitations/exchange", { token });
}

/** The backend returns a generic 401 for every failure mode, with a
 * machine-readable `reason` in the body (never a distinct HTTP status
 * per case — see invitation_service.py) so a blind guesser can't learn
 * whether a token/employee exists. Unwraps that reason for UI copy. */
export function invitationFailureReason(err: unknown): InvitationFailureReason {
  if (err instanceof ApiError) {
    try {
      const body = JSON.parse(err.message) as { detail?: { reason?: string } };
      const reason = body.detail?.reason;
      if (reason && (KNOWN_REASONS as readonly string[]).includes(reason)) {
        return reason as InvitationFailureReason;
      }
    } catch {
      // Non-JSON body (e.g. a network-level failure) — falls through.
    }
  }
  return "invalid";
}

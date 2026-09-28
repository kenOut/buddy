"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { SCENES, sceneFromPathname } from "@/lib/scenes";
import type { MissionAssignment, OnboardingBundle, OnboardingSession, SceneKey } from "@/lib/types";

interface OnboardingContextValue {
  bundle: OnboardingBundle | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  goToScene: (scene: SceneKey) => void;
  updateAssignment: (assignment: MissionAssignment) => void;
  resetDemo: () => Promise<void>;
}

const OnboardingContext = createContext<OnboardingContextValue | null>(null);

export function OnboardingProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [bundle, setBundle] = useState<OnboardingBundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Set right before resetDemo replaces `bundle` out from under the current
  // URL (scene reset to "welcome" while the user is still looking at
  // /onboarding/completion) — skips exactly the one sync-effect run that
  // would otherwise read that as a mismatch and PATCH the session's scene
  // back to "completion" before the router.push below ever lands.
  const suppressSceneSyncRef = useRef(false);

  const load = useCallback(async () => {
    try {
      // The MVP has exactly one demo identity, resolved server-side from
      // config — no caller-supplied identifier selects whose data comes
      // back (see backend `GET /onboarding/bundle/demo`).
      const data = await api.get<OnboardingBundle>("/onboarding/bundle/demo");
      setBundle(data);
      setError(null);
    } catch {
      setError("Could not reach the Buddy backend. Is the FastAPI server running on :8000?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Fetch-on-mount: state updates happen after the internal `await`, in a
    // microtask, never synchronously during this effect's render pass.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const refetch = useCallback(() => {
    setLoading(true);
    return load();
  }, [load]);

  // The URL is the single authoritative source for "which scene is on
  // screen" (see lib/scenes.ts#sceneFromPathname). This effect keeps the
  // persisted session in sync with it for every kind of navigation —
  // Next/Back buttons, browser back/forward, and direct/deep links — so the
  // progress indicator (which reads the session) can never silently
  // disagree with what's rendered. A failed sync is non-fatal: the URL
  // still drives the UI correctly, only the resume point may lag.
  useEffect(() => {
    if (!bundle) return;
    if (suppressSceneSyncRef.current) {
      suppressSceneSyncRef.current = false;
      return;
    }
    const scene = sceneFromPathname(pathname);
    if (!scene || scene.key === bundle.session.current_scene) return;

    api
      .patch<OnboardingSession>(`/onboarding/sessions/${bundle.session.id}`, {
        current_scene: scene.key,
      })
      .then((session) => {
        setBundle((prev) => (prev ? { ...prev, session } : prev));
      })
      .catch(() => {
        // Session persistence will retry the next time the route changes.
      });
  }, [pathname, bundle]);

  const goToScene = useCallback(
    (scene: SceneKey) => {
      const target = SCENES.find((s) => s.key === scene);
      if (!target) return;
      router.push(`/onboarding/${target.slug}`);
    },
    [router]
  );

  const resetDemo = useCallback(async () => {
    // Demo/presentation tooling only — see the backend endpoint's own
    // docstring. Returns the full fresh bundle in one call, so this
    // doesn't need a second round trip through `refetch`.
    const fresh = await api.post<OnboardingBundle>("/onboarding/demo/reset");
    suppressSceneSyncRef.current = true;
    setBundle(fresh);
    router.push("/onboarding/welcome");
  }, [router]);

  const updateAssignment = useCallback((assignment: MissionAssignment) => {
    setBundle((prev) =>
      prev
        ? {
            ...prev,
            mission_assignments: prev.mission_assignments.map((a) =>
              a.id === assignment.id ? assignment : a
            ),
          }
        : prev
    );
  }, []);

  return (
    <OnboardingContext.Provider
      value={{ bundle, loading, error, refetch, goToScene, updateAssignment, resetDemo }}
    >
      {children}
    </OnboardingContext.Provider>
  );
}

export function useOnboarding() {
  const ctx = useContext(OnboardingContext);
  if (!ctx) throw new Error("useOnboarding must be used within OnboardingProvider");
  return ctx;
}

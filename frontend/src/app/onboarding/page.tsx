"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { SCENES } from "@/lib/scenes";
import { useOnboarding } from "@/lib/onboarding-context";

/**
 * Resumes the employee where they left off. `OnboardingChrome` (the parent
 * layout) only renders this once `bundle` is loaded, so the persisted
 * session's `current_scene` is available immediately — no reset to Welcome.
 */
export default function OnboardingIndexPage() {
  const router = useRouter();
  const { bundle } = useOnboarding();

  useEffect(() => {
    if (!bundle) return;
    const scene =
      SCENES.find((s) => s.key === bundle.session.current_scene) ?? SCENES[0];
    router.replace(`/onboarding/${scene.slug}`);
  }, [bundle, router]);

  return null;
}

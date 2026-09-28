"use client";

import { usePathname } from "next/navigation";
import clsx from "clsx";

import { ProgressAnimation } from "@/components/animations/ProgressAnimation";
import { SCENES, sceneFromPathname } from "@/lib/scenes";

export function ProgressIndicator() {
  const pathname = usePathname();
  const scene = sceneFromPathname(pathname);

  // Routes outside the fixed 8-scene onboarding journey (e.g. a Quest
  // Workspace at /onboarding/quests/[questId]) aren't one of those
  // scenes at all — showing "Step 1 of 8 / 0%" here would be actively
  // misleading rather than merely inapplicable, so render nothing
  // instead of defaulting to a fake position.
  if (!scene) return null;

  const currentIndex = SCENES.findIndex((s) => s.key === scene.key);
  const percent = Math.round((currentIndex / (SCENES.length - 1)) * 100);

  return (
    <div className="w-full">
      <div className="mb-3 flex items-center justify-between text-xs text-buddy-muted">
        <span>
          Step {currentIndex + 1} of {SCENES.length}
        </span>
        <span>{percent}%</span>
      </div>
      <ProgressAnimation percent={percent} />
      <div className="mt-4 hidden gap-1 sm:flex">
        {SCENES.map((s, i) => (
          <div
            key={s.key}
            className={clsx(
              "flex-1 truncate text-center text-[10px] uppercase tracking-wide",
              i <= currentIndex ? "text-buddy-primary" : "text-buddy-muted/60"
            )}
          >
            {s.short}
          </div>
        ))}
      </div>
    </div>
  );
}

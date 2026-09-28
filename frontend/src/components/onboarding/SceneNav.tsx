"use client";

import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/Button";
import { useOnboarding } from "@/lib/onboarding-context";
import { nextScene, prevScene, sceneFromPathname } from "@/lib/scenes";

interface SceneNavProps {
  nextLabel?: string;
  onNext?: () => void | Promise<void>;
  nextDisabled?: boolean;
  hideBack?: boolean;
}

export function SceneNav({ nextLabel, onNext, nextDisabled, hideBack }: SceneNavProps) {
  const pathname = usePathname();
  const { goToScene } = useOnboarding();
  const current = sceneFromPathname(pathname);
  const prev = current ? prevScene(current.key) : undefined;
  const next = current ? nextScene(current.key) : undefined;

  const handleNext = async () => {
    if (onNext) {
      await onNext();
      return;
    }
    if (next) goToScene(next.key);
  };

  return (
    <>
      {!hideBack && prev ? (
        <Button variant="ghost" onClick={() => goToScene(prev.key)}>
          Back
        </Button>
      ) : (
        <span />
      )}
      {(next || onNext) && (
        <Button onClick={handleNext} disabled={nextDisabled}>
          {nextLabel ?? `Continue to ${next?.short ?? "next"}`}
        </Button>
      )}
    </>
  );
}

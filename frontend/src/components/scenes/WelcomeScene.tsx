"use client";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { BUDDY_NAME } from "@/components/buddy/buddyStates";
import { BuddySpeech } from "@/components/buddy/BuddySpeech";
import { FadeIn } from "@/components/animations/FadeIn";
import { SlideUp } from "@/components/animations/SlideUp";
import { SceneNav } from "@/components/onboarding/SceneNav";
import { useOnboarding } from "@/lib/onboarding-context";

export function WelcomeScene() {
  const { bundle } = useOnboarding();
  if (!bundle) return null;

  const firstName = bundle.employee.full_name.split(" ")[0];

  return (
    <div className="mx-auto flex max-w-3xl flex-col items-center gap-8 py-6 text-center sm:py-10">
      <FadeIn duration={0.9}>
        <div className="mx-auto h-32 w-32 sm:h-44 sm:w-44">
          <BuddyIllustration state="welcome" label={`${BUDDY_NAME} waving hello`} />
        </div>
      </FadeIn>

      <SlideUp delay={0.15} duration={0.5} className="w-full">
        <h1 className="font-heading text-3xl font-bold text-buddy-navy sm:text-5xl">
          Hey {firstName} 👋
        </h1>
      </SlideUp>

      <SlideUp delay={0.3} duration={0.45} className="w-full max-w-md">
        <BuddySpeech tail="bottom" className="text-left">
          <p className="font-heading text-sm font-bold uppercase tracking-wide text-buddy-primary">
            {BUDDY_NAME}
          </p>
          <p className="mt-2">
            Great, you&rsquo;re done with P&amp;C. I&rsquo;m just here to ease you in and out of
            the department — catch my drift? Welcome to your department.
          </p>
        </BuddySpeech>
      </SlideUp>

      <SlideUp delay={0.45} duration={0.4} className="mt-2 w-full">
        <div className="flex items-center justify-center gap-3">
          <SceneNav nextLabel="Let's get started" hideBack />
        </div>
      </SlideUp>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { usePathname } from "next/navigation";

const variants = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -20 },
};

const reducedVariants = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
};

/** Scene-to-scene transitions: 500–800ms per the animation spec. */
export function SceneTransition({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const reduceMotion = useReducedMotion();

  // Next.js wraps every <Link> navigation in startTransition, so `pathname`
  // can change mid-render across more than one concurrent render pass
  // before anything commits. Reading it directly as the AnimatePresence
  // key let two such passes race: Framer Motion would run a real
  // animation from one pass (visible in its own onAnimationComplete
  // callback firing "animate") while a second, stale-state pass's commit
  // landed afterward and overwrote the DOM back to the exit style —
  // motion.div stuck at opacity: 0 forever, on every return visit to
  // /onboarding/missions specifically (its destination is a static
  // segment; the forward direction's destination is dynamic and never
  // hit this race). Updating the key from an effect instead of during
  // render means it only ever changes once a navigation has fully
  // committed, so there's exactly one animation per transition, never
  // two racing generations.
  const [renderedPathname, setRenderedPathname] = useState(pathname);
  useEffect(() => {
    // Deliberately after commit, not computed during render — see the
    // comment above. Synchronous, nothing async to defer this into.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRenderedPathname(pathname);
  }, [pathname]);

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={renderedPathname}
        variants={reduceMotion ? reducedVariants : variants}
        initial="initial"
        animate="animate"
        exit="exit"
        transition={{ duration: reduceMotion ? 0.15 : 0.55, ease: "easeInOut" }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}

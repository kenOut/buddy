"use client";

import { motion, useReducedMotion } from "motion/react";

import { BuddyExpression } from "@/components/buddy/BuddyExpression";
import { BUDDY_STATES, type BuddyState } from "@/components/buddy/buddyStates";

interface BuddyIllustrationProps {
  state?: BuddyState;
  className?: string;
  /** Decorative by default. Pass a label when Buddy is the sole carrier of
   * meaning on screen (rare — most scenes pair Buddy with real text). */
  label?: string;
}

/**
 * Buddy — same body/head/antenna silhouette in every state, so identity
 * stays recognizable. Only expression, pose and glow change.
 */
export function BuddyIllustration({ state = "friendly", className, label }: BuddyIllustrationProps) {
  const reduceMotion = useReducedMotion();
  const config = BUDDY_STATES[state];
  const { pose, glow, eyes, mouth } = config;

  const bobAmplitude = reduceMotion ? 0 : pose.bobAmplitude;
  const bobDuration = pose.bobDuration;

  return (
    <motion.div
      className={className}
      role={label ? "img" : "presentation"}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      animate={reduceMotion ? { y: 0 } : { y: [0, -bobAmplitude, 0] }}
      transition={{ duration: bobDuration, repeat: reduceMotion ? 0 : Infinity, ease: "easeInOut" }}
    >
      <svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg" className="h-full w-full">
        {glow && (
          <motion.circle
            cx="100"
            cy="100"
            r="90"
            fill={glow.color}
            initial={false}
            animate={
              reduceMotion
                ? { opacity: glow.intensity }
                : { opacity: [glow.intensity * 0.6, glow.intensity, glow.intensity * 0.6] }
            }
            transition={{ duration: 3, repeat: reduceMotion ? 0 : Infinity, ease: "easeInOut" }}
          />
        )}

        <ellipse cx="100" cy="182" rx="46" ry="8" fill="var(--buddy-navy)" opacity="0.08" />

        <motion.g
          animate={reduceMotion ? { rotate: pose.bodyTilt } : { rotate: [pose.bodyTilt - 2, pose.bodyTilt + 2, pose.bodyTilt - 2] }}
          transition={{ duration: bobDuration + 1, repeat: reduceMotion ? 0 : Infinity, ease: "easeInOut" }}
          style={{ transformOrigin: "100px 110px" }}
        >
          {/* left arm */}
          <motion.rect
            x="26"
            y="90"
            width="18"
            height="46"
            rx="9"
            fill="var(--buddy-coral)"
            animate={{ rotate: pose.leftArmRotate }}
            transition={{ type: "spring", stiffness: 140, damping: 14 }}
            style={{ transformOrigin: "35px 92px" }}
          />
          {/* right arm */}
          <motion.rect
            x="156"
            y="90"
            width="18"
            height="46"
            rx="9"
            fill="var(--buddy-coral)"
            animate={
              pose.waving && !reduceMotion
                ? { rotate: [pose.rightArmRotate - 12, pose.rightArmRotate + 12, pose.rightArmRotate - 12] }
                : { rotate: pose.rightArmRotate }
            }
            transition={
              pose.waving && !reduceMotion
                ? { duration: 0.9, repeat: Infinity, ease: "easeInOut" }
                : { type: "spring", stiffness: 140, damping: 14 }
            }
            style={{ transformOrigin: "165px 92px" }}
          />

          <rect x="55" y="70" width="90" height="80" rx="28" fill="var(--buddy-cyan)" />
          <circle cx="100" cy="55" r="42" fill="var(--buddy-cyan)" />

          <BuddyExpression eyes={eyes} mouth={mouth} />

          <circle cx="100" cy="18" r="6" fill="var(--buddy-sunrise)" />
          <rect x="98" y="24" width="4" height="14" fill="var(--buddy-sunrise)" />
        </motion.g>
      </svg>
    </motion.div>
  );
}

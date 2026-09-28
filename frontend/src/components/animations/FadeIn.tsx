"use client";

import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

interface FadeInProps {
  children: ReactNode;
  className?: string;
  delay?: number;
  /** Cards: 300–450ms. Scene-level emotional beats: 800–1200ms. */
  duration?: number;
}

export function FadeIn({ children, className, delay = 0, duration = 0.4 }: FadeInProps) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: reduceMotion ? 0.01 : duration, delay: reduceMotion ? 0 : delay, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}

"use client";

import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

interface SlideUpProps {
  children: ReactNode;
  className?: string;
  delay?: number;
  /** Cards: 300–450ms is the intended range. */
  duration?: number;
  distance?: number;
}

export function SlideUp({ children, className, delay = 0, duration = 0.35, distance = 16 }: SlideUpProps) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: reduceMotion ? 0 : distance }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduceMotion ? 0.01 : duration, delay: reduceMotion ? 0 : delay, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}

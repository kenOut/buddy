"use client";

import { motion, useReducedMotion, type Variants } from "motion/react";
import { Children, type ReactNode } from "react";

interface StaggerChildrenProps {
  children: ReactNode;
  className?: string;
  itemClassName?: string;
  /** Seconds between each child revealing. */
  staggerDelay?: number;
}

/**
 * Reveals children one at a time instead of all at once — used for the
 * team roster, role responsibility cards, and the mission list so nothing
 * dumps onto the screen simultaneously.
 */
export function StaggerChildren({
  children,
  className,
  itemClassName,
  staggerDelay = 0.12,
}: StaggerChildrenProps) {
  const reduceMotion = useReducedMotion();

  const container: Variants = {
    hidden: {},
    visible: {
      transition: { staggerChildren: reduceMotion ? 0 : staggerDelay },
    },
  };

  const item: Variants = {
    hidden: { opacity: 0, y: reduceMotion ? 0 : 14 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: reduceMotion ? 0.01 : 0.4, ease: "easeOut" },
    },
  };

  return (
    <motion.div className={className} initial="hidden" animate="visible" variants={container}>
      {Children.map(children, (child, i) => (
        <motion.div key={i} className={itemClassName} variants={item}>
          {child}
        </motion.div>
      ))}
    </motion.div>
  );
}

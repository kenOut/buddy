"use client";

import { motion, useReducedMotion } from "motion/react";
import { useMemo } from "react";

const PALETTE = ["var(--buddy-cyan)", "var(--buddy-aurora)", "var(--buddy-sunrise)", "var(--buddy-coral)"];

interface Particle {
  id: number;
  x: number;
  delay: number;
  color: string;
  size: number;
  rotate: number;
}

/**
 * A small celebratory burst for the Completion scene. Cheap by design — a
 * dozen absolutely-positioned dots, no external confetti library. Renders
 * nothing when the user prefers reduced motion, per the accessibility
 * requirement to drop non-essential particle effects.
 */
export function Celebration({ count = 14 }: { count?: number }) {
  const reduceMotion = useReducedMotion();

  const particles = useMemo<Particle[]>(
    () =>
      Array.from({ length: count }, (_, i) => ({
        id: i,
        x: (i / count) * 100 + (Math.sin(i * 7) * 4),
        delay: (i % 5) * 0.08,
        color: PALETTE[i % PALETTE.length],
        size: 6 + (i % 3) * 3,
        rotate: (i * 47) % 360,
      })),
    [count]
  );

  if (reduceMotion) return null;

  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      {particles.map((p) => (
        <motion.span
          key={p.id}
          className="absolute top-1/3 rounded-sm"
          style={{
            left: `${p.x}%`,
            width: p.size,
            height: p.size * 0.4,
            backgroundColor: p.color,
          }}
          initial={{ y: 0, opacity: 0, rotate: 0 }}
          animate={{ y: [0, -40, 160], opacity: [0, 1, 0], rotate: p.rotate }}
          transition={{ duration: 1.6, delay: p.delay, ease: "easeOut" }}
        />
      ))}
    </div>
  );
}

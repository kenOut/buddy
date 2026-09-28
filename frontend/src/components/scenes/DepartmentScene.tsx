"use client";

import { motion, useReducedMotion } from "motion/react";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { BuddySpeech } from "@/components/buddy/BuddySpeech";
import { FadeIn } from "@/components/animations/FadeIn";
import { StaggerChildren } from "@/components/animations/StaggerChildren";
import { Card } from "@/components/ui/Card";
import { SceneNav } from "@/components/onboarding/SceneNav";
import { useOnboarding } from "@/lib/onboarding-context";

/** Generic systems/network graphic — deliberately not tied to any one
 * department's name, so it reads sensibly for Engineering, Design, or
 * anything else without hardcoding department-specific content. */
function SystemsVisual() {
  const reduceMotion = useReducedMotion();
  const nodes = [
    { cx: 100, cy: 40 },
    { cx: 40, cy: 110 },
    { cx: 160, cy: 110 },
    { cx: 70, cy: 175 },
    { cx: 130, cy: 175 },
  ];
  const edges: [number, number][] = [
    [0, 1],
    [0, 2],
    [1, 3],
    [2, 4],
    [1, 2],
  ];

  return (
    <svg viewBox="0 0 200 210" className="h-full w-full" aria-hidden="true">
      {edges.map(([a, b], i) => (
        <motion.line
          key={i}
          x1={nodes[a].cx}
          y1={nodes[a].cy}
          x2={nodes[b].cx}
          y2={nodes[b].cy}
          stroke="var(--buddy-cyan)"
          strokeWidth="2"
          strokeOpacity="0.35"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: reduceMotion ? 0.01 : 0.8, delay: i * 0.1, ease: "easeOut" }}
        />
      ))}
      {nodes.map((n, i) => (
        <motion.circle
          key={i}
          cx={n.cx}
          cy={n.cy}
          r={i === 0 ? 14 : 10}
          fill={i === 0 ? "var(--buddy-cyan)" : "var(--buddy-aurora)"}
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: reduceMotion ? 0.01 : 0.4, delay: 0.3 + i * 0.12, ease: "backOut" }}
        />
      ))}
    </svg>
  );
}

export function DepartmentScene() {
  const { bundle } = useOnboarding();
  if (!bundle) return null;

  const { department, projects } = bundle;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-8 py-4">
      <div className="grid grid-cols-1 items-center gap-8 sm:grid-cols-[1fr_180px]">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-buddy-primary">
            Department
          </p>
          <h1 className="font-heading text-3xl font-bold text-buddy-navy sm:text-4xl">
            {department?.name ?? "Your department"}
          </h1>
          {department?.description && (
            <p className="mt-3 max-w-lg text-base text-buddy-text-secondary">
              {department.description}
            </p>
          )}
        </div>
        <FadeIn duration={0.8} className="mx-auto h-32 w-32 sm:h-40 sm:w-40">
          <SystemsVisual />
        </FadeIn>
      </div>

      <div className="flex items-start gap-3 sm:gap-4">
        <div className="h-14 w-14 shrink-0">
          <BuddyIllustration state="guide" />
        </div>
        <BuddySpeech className="flex-1">
          You&rsquo;re joining <strong>{department?.name ?? "this department"}</strong>. Here&rsquo;s
          what&rsquo;s already in motion.
        </BuddySpeech>
      </div>

      {projects.length > 0 && (
        <div>
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-buddy-muted">
            Active projects
          </p>
          <StaggerChildren className="grid grid-cols-1 gap-3 sm:grid-cols-2" staggerDelay={0.1}>
            {projects.map((project) => (
              <Card key={project.id} className="bg-buddy-cloud/60">
                <p className="font-medium text-buddy-text-primary">{project.name}</p>
                {project.description && (
                  <p className="mt-1 text-sm text-buddy-text-secondary">{project.description}</p>
                )}
              </Card>
            ))}
          </StaggerChildren>
        </div>
      )}

      <div className="flex items-center justify-between pt-2">
        <SceneNav />
      </div>
    </div>
  );
}

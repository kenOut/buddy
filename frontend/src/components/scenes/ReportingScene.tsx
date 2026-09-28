"use client";

import { motion, useReducedMotion } from "motion/react";

import { BuddyIllustration } from "@/components/buddy/BuddyIllustration";
import { BuddySpeech } from "@/components/buddy/BuddySpeech";
import { SceneNav } from "@/components/onboarding/SceneNav";
import { useOnboarding } from "@/lib/onboarding-context";
import type { EmployeeSummary } from "@/lib/types";

function initials(name: string) {
  return name
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

interface ChainNode {
  label: string;
  title: string;
  subtitle?: string;
  initials: string;
  accent: string;
}

function Connector({ delay }: { delay: number }) {
  const reduceMotion = useReducedMotion();
  return (
    <motion.div
      className="mx-auto h-8 w-0.5 bg-buddy-border"
      initial={{ scaleY: reduceMotion ? 1 : 0, opacity: reduceMotion ? 1 : 0 }}
      animate={{ scaleY: 1, opacity: 1 }}
      style={{ transformOrigin: "top" }}
      transition={{ duration: reduceMotion ? 0.01 : 0.35, delay: reduceMotion ? 0 : delay, ease: "easeOut" }}
    />
  );
}

function ChainCard({ node, delay }: { node: ChainNode; delay: number }) {
  const reduceMotion = useReducedMotion();
  return (
    <motion.div
      initial={{ opacity: 0, y: reduceMotion ? 0 : 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduceMotion ? 0.01 : 0.4, delay: reduceMotion ? 0 : delay, ease: "easeOut" }}
      className="mx-auto flex w-full max-w-sm items-center gap-3 rounded-xl border border-buddy-border bg-buddy-surface p-4 shadow-sm"
    >
      <div
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-sm font-semibold text-white"
        style={{ backgroundColor: node.accent }}
      >
        {node.initials}
      </div>
      <div className="min-w-0 text-left">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-buddy-muted">
          {node.label}
        </p>
        <p className="truncate font-medium text-buddy-text-primary">{node.title}</p>
        {node.subtitle && (
          <p className="truncate text-xs text-buddy-text-secondary">{node.subtitle}</p>
        )}
      </div>
    </motion.div>
  );
}

export function ReportingScene() {
  const { bundle } = useOnboarding();
  if (!bundle) return null;

  const { employee, manager, supervisor, department } = bundle;

  const nodes: ChainNode[] = [
    {
      label: "You",
      title: employee.full_name,
      subtitle: employee.job_title ?? undefined,
      initials: initials(employee.full_name),
      accent: "var(--buddy-cyan)",
    },
    ...(supervisor
      ? [personNode("Supervisor", supervisor, "var(--buddy-aurora)")]
      : []),
    ...(manager ? [personNode("Manager", manager, "var(--buddy-sunrise)")] : []),
    {
      label: "Department",
      title: department?.name ?? "—",
      initials: (department?.name ?? "?").slice(0, 2).toUpperCase(),
      accent: "var(--buddy-coral)",
    },
  ];

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-8 py-4">
      <div className="flex items-start gap-3 sm:gap-4">
        <div className="h-14 w-14 shrink-0">
          <BuddyIllustration state="guide" />
        </div>
        <BuddySpeech className="flex-1">
          <p className="font-heading text-lg font-bold text-buddy-navy">Your reporting line</p>
          <p className="mt-1 text-buddy-text-secondary">
            Your supervisor is your day-to-day guide. Your manager sets direction and goals.
          </p>
        </BuddySpeech>
      </div>

      <div>
        {nodes.map((node, i) => (
          <div key={`${node.label}-${node.title}`}>
            <ChainCard node={node} delay={i * 0.25} />
            {i < nodes.length - 1 && <Connector delay={i * 0.25 + 0.15} />}
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between pt-2">
        <SceneNav />
      </div>
    </div>
  );
}

function personNode(label: string, person: EmployeeSummary, accent: string): ChainNode {
  return {
    label,
    title: person.full_name,
    subtitle: person.job_title ?? undefined,
    initials: initials(person.full_name),
    accent,
  };
}

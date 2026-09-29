"use client";

import { useState } from "react";

import { StaggerChildren } from "@/components/animations/StaggerChildren";
import { resolveAvatarUrl } from "@/lib/api";
import type { EmployeeSummary } from "@/lib/types";

/** Row sizes from back to front (GK -> DEF -> MID -> FWD) for however
 * many starters we actually have (capped at 11, soccer's own real
 * limit). Real formations for 11: 4-3-3. Smaller real teams get a
 * proportionally smaller shape rather than an invented full XI —
 * nothing here is fabricated about any person, only the row a real
 * teammate's real chip happens to sit in. */
const ROW_PATTERNS: Record<number, number[]> = {
  11: [1, 4, 3, 3], // 4-3-3
  10: [1, 4, 3, 2],
  9: [1, 3, 3, 2],
  8: [1, 3, 2, 2],
  7: [1, 3, 2, 1],
  6: [1, 2, 2, 1],
  5: [1, 2, 1, 1],
  4: [1, 2, 1],
  3: [1, 1, 1],
  2: [1, 1],
  1: [1],
};

function rowsFor(starterCount: number): number[] {
  return ROW_PATTERNS[starterCount] ?? (starterCount > 0 ? [starterCount] : []);
}

function initials(name: string) {
  return name
    .split(" ")
    .map((part) => part[0])
    .filter(Boolean)
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function firstName(name: string) {
  return name.split(" ")[0] ?? name;
}

const TEAM_PALETTE = [
  { chip: "bg-buddy-primary", text: "text-white", dot: "bg-buddy-primary" },
  { chip: "bg-buddy-sunrise", text: "text-buddy-navy", dot: "bg-buddy-sunrise" },
  { chip: "bg-buddy-coral", text: "text-white", dot: "bg-buddy-coral" },
  { chip: "bg-buddy-navy", text: "text-white", dot: "bg-buddy-navy" },
];

/**
 * A real photo when `avatar_url` resolves to one (seeded placeholder
 * headshots, or an admin-uploaded photo — see the employee detail
 * page's upload control) — falling back to the same colored-initials
 * chip as before if there's no avatar yet, or the image fails to load.
 * `key={url}` resets the failed-load state when the avatar itself
 * changes (e.g. right after an upload), instead of getting stuck
 * showing the fallback for the old, now-different URL.
 */
function Avatar({
  person,
  sizeClassName,
  textSizeClassName,
  palette,
}: {
  person: EmployeeSummary;
  sizeClassName: string;
  textSizeClassName: string;
  palette: { chip: string; text: string };
}) {
  const [failed, setFailed] = useState(false);
  const url = resolveAvatarUrl(person.avatar_url);

  if (url && !failed) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- external/backend-served photo, not a static build asset.
      <img
        key={url}
        src={url}
        alt={person.full_name}
        className={`${sizeClassName} rounded-full object-cover ring-2 ring-white/80 shadow-md`}
        onError={() => setFailed(true)}
      />
    );
  }

  return (
    <div
      className={`flex items-center justify-center rounded-full ${sizeClassName} ${palette.chip} ${palette.text} ${textSizeClassName} font-bold ring-2 ring-white/80 shadow-md`}
    >
      {initials(person.full_name)}
    </div>
  );
}

function PlayerChip({
  person,
  number,
  colorIndex,
}: {
  person: EmployeeSummary;
  number: number;
  colorIndex: number;
}) {
  const palette = TEAM_PALETTE[colorIndex % TEAM_PALETTE.length];
  return (
    <div className="flex flex-col items-center gap-1.5" title={`${person.full_name} — ${person.job_title ?? ""}`}>
      <div className="relative">
        <Avatar
          person={person}
          sizeClassName="h-11 w-11 sm:h-16 sm:w-16"
          textSizeClassName="text-base sm:text-lg"
          palette={palette}
        />
        <span className="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-white text-[10px] font-bold text-buddy-navy shadow">
          {number}
        </span>
      </div>
      <div className="max-w-[82px] rounded-md bg-white/95 px-1.5 py-0.5 text-center shadow-sm sm:max-w-[110px]">
        <p className="truncate text-[11px] leading-tight font-semibold text-buddy-navy sm:text-xs">
          {firstName(person.full_name)}
        </p>
        <p className="truncate text-[9px] leading-tight text-buddy-muted sm:text-[10px]">
          {person.job_title ?? " "}
        </p>
      </div>
    </div>
  );
}

/**
 * "Meet your team," styled as a lineup graphic instead of a plain list —
 * real names, real titles, real sub-team grouping, just arranged on a
 * pitch. The formation shape and jersey numbers are pure decoration
 * (like drawing a soccer ball next to the heading would be); nothing
 * about a real person's actual role or position is asserted by where
 * their chip happens to sit — that's why there's no GK/DEF/MID/FWD
 * label on any individual chip, only the row shape itself.
 */
export function TeamFormation({ peers }: { peers: EmployeeSummary[] }) {
  const starters = peers.slice(0, 11);
  const bench = peers.slice(11);
  const rows = rowsFor(starters.length);

  // Colour-code by each person's real `team` field (e.g. TechOps/FinOps)
  // so that real grouping survives the redesign — just as a colour and
  // a legend dot instead of a section header.
  const teamOrder: string[] = [];
  for (const p of peers) {
    const key = p.team ?? "Team";
    if (!teamOrder.includes(key)) teamOrder.push(key);
  }
  const colorIndexOf = (p: EmployeeSummary) => teamOrder.indexOf(p.team ?? "Team");

  // Pure, no running-total variable to mutate: turn row sizes into
  // cumulative start offsets first (fold, not a loop with reassignment),
  // then slice against those.
  const rowStarts = rows.reduce<number[]>((offsets, size, i) => {
    offsets.push(i === 0 ? 0 : offsets[i - 1] + rows[i - 1]);
    return offsets;
  }, []);
  const rowMembers = rows.map((size, i) => starters.slice(rowStarts[i], rowStarts[i] + size));

  return (
    <div className="flex flex-col gap-4">
      <div className="relative overflow-hidden rounded-2xl border border-buddy-border shadow-inner">
        <div
          className="absolute inset-0"
          style={{
            backgroundImage:
              "repeating-linear-gradient(180deg, #049944 0px, #049944 44px, #03863a 44px, #03863a 88px)",
          }}
          aria-hidden="true"
        />
        {/* halfway line + center circle, purely decorative pitch markings */}
        <div className="absolute top-1/2 right-3 left-3 h-px -translate-y-1/2 bg-white/40" aria-hidden="true" />
        <div
          className="absolute top-1/2 left-1/2 h-16 w-16 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/40 sm:h-20 sm:w-20"
          aria-hidden="true"
        />
        <div className="absolute inset-2 rounded-xl border border-white/25" aria-hidden="true" />

        <StaggerChildren
          className="relative flex flex-col justify-between gap-6 px-3 py-7 sm:gap-8 sm:px-6 sm:py-9"
          staggerDelay={0.06}
        >
          {rowMembers.map((members, rowIndex) => (
            <div key={rowIndex} className="flex items-start justify-evenly gap-2 sm:gap-4">
              {members.map((person) => (
                <PlayerChip
                  key={person.id}
                  person={person}
                  number={peers.indexOf(person) + 1}
                  colorIndex={colorIndexOf(person)}
                />
              ))}
            </div>
          ))}
        </StaggerChildren>
      </div>

      {teamOrder.length > 1 && (
        <div className="flex flex-wrap items-center justify-center gap-4 text-xs text-buddy-muted">
          {teamOrder.map((team, i) => (
            <span key={team} className="flex items-center gap-1.5">
              <span
                className={`h-2.5 w-2.5 rounded-full ${TEAM_PALETTE[i % TEAM_PALETTE.length].dot}`}
                aria-hidden="true"
              />
              {team}
            </span>
          ))}
        </div>
      )}

      {bench.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-semibold tracking-wide text-buddy-muted uppercase">
            Bench &middot; {bench.length} more {bench.length === 1 ? "teammate" : "teammates"}
          </p>
          <div className="flex flex-wrap gap-2">
            {bench.map((person) => (
              <div
                key={person.id}
                className="flex items-center gap-2 rounded-full border border-buddy-border bg-background/40 py-1.5 pr-3 pl-1.5"
              >
                <Avatar
                  person={person}
                  sizeClassName="h-9 w-9 shrink-0"
                  textSizeClassName="text-xs"
                  palette={TEAM_PALETTE[colorIndexOf(person) % TEAM_PALETTE.length]}
                />
                <div className="min-w-0">
                  <p className="truncate text-xs font-medium text-foreground">{person.full_name}</p>
                  <p className="truncate text-[10px] text-buddy-muted">{person.job_title}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

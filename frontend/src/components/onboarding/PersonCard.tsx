"use client";

import { useState } from "react";

import { resolveAvatarUrl } from "@/lib/api";
import type { EmployeeSummary } from "@/lib/types";

function initials(name: string) {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

export function PersonCard({
  person,
  role,
}: {
  person: EmployeeSummary;
  role?: string;
}) {
  const [failed, setFailed] = useState(false);
  const url = resolveAvatarUrl(person.avatar_url);

  return (
    <div className="flex items-center gap-3 rounded-xl border border-buddy-border bg-background/40 p-4">
      {url && !failed ? (
        // eslint-disable-next-line @next/next/no-img-element -- backend-served/external photo, not a static build asset.
        <img
          key={url}
          src={url}
          alt={person.full_name}
          className="h-11 w-11 shrink-0 rounded-full object-cover"
          onError={() => setFailed(true)}
        />
      ) : (
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-buddy-primary/10 text-sm font-semibold text-buddy-primary">
          {initials(person.full_name)}
        </div>
      )}
      <div className="min-w-0">
        <p className="truncate font-medium text-foreground">{person.full_name}</p>
        <p className="truncate text-xs text-buddy-muted">{role ?? person.job_title}</p>
      </div>
    </div>
  );
}

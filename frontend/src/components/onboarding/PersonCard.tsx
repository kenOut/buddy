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
  return (
    <div className="flex items-center gap-3 rounded-xl border border-buddy-border bg-background/40 p-4">
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-buddy-primary/10 text-sm font-semibold text-buddy-primary">
        {initials(person.full_name)}
      </div>
      <div className="min-w-0">
        <p className="truncate font-medium text-foreground">{person.full_name}</p>
        <p className="truncate text-xs text-buddy-muted">{role ?? person.job_title}</p>
      </div>
    </div>
  );
}

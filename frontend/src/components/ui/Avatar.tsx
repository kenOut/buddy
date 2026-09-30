const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join("");

export function Avatar({ name, size = "md" }: { name: string; size?: "sm" | "md" }) {
  const dims = size === "sm" ? "h-7 w-7 text-[10px]" : "h-9 w-9 text-xs";
  return (
    <span
      aria-hidden
      className={`inline-flex ${dims} shrink-0 items-center justify-center rounded-full bg-buddy-primary/15 font-semibold text-buddy-primary`}
    >
      {initials(name) || "?"}
    </span>
  );
}

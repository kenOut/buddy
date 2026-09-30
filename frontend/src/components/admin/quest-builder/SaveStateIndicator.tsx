export type BuilderSaveState = "idle" | "saving" | "saved" | "error";

export function SaveStateIndicator({
  state,
  onRetry,
}: {
  state: BuilderSaveState;
  onRetry?: () => void;
}) {
  if (state === "idle") return null;
  if (state === "saving") {
    return <span className="text-xs text-buddy-muted">Saving…</span>;
  }
  if (state === "saved") {
    return <span className="text-xs text-emerald-700 dark:text-emerald-400">Saved</span>;
  }
  return (
    <span className="flex items-center gap-2 text-xs text-red-600 dark:text-red-400">
      Couldn&rsquo;t save.
      {onRetry && (
        <button type="button" onClick={onRetry} className="font-medium underline">
          Retry
        </button>
      )}
    </span>
  );
}

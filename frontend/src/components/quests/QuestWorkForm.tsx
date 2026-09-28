export type SaveState = "idle" | "saving" | "saved" | "error";

type WorkField = "findings" | "reasoning" | "solution";

/** The generic, quest-type-agnostic work inputs (Stage 4 spec §13) —
 * the same three fields regardless of whether this is an INVESTIGATE,
 * BUILD, or DESIGN quest. */
export function QuestWorkForm({
  findings,
  reasoning,
  solution,
  onChange,
  saveState,
  onRetry,
  disabled,
}: {
  findings: string;
  reasoning: string;
  solution: string;
  onChange: (field: WorkField, value: string) => void;
  saveState: SaveState;
  onRetry: () => void;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-4">
      <Field
        id="quest-findings"
        label="What did you find?"
        value={findings}
        placeholder="What does the evidence show?"
        onChange={(v) => onChange("findings", v)}
        disabled={disabled}
      />
      <Field
        id="quest-reasoning"
        label="Explain your reasoning"
        value={reasoning}
        placeholder="How did you get to that conclusion?"
        onChange={(v) => onChange("reasoning", v)}
        disabled={disabled}
      />
      <Field
        id="quest-solution"
        label="Your proposed solution"
        value={solution}
        placeholder="What would you do about it?"
        onChange={(v) => onChange("solution", v)}
        disabled={disabled}
      />
      <SaveStatus state={saveState} onRetry={onRetry} />
    </div>
  );
}

function Field({
  id,
  label,
  value,
  placeholder,
  onChange,
  disabled,
}: {
  id: string;
  label: string;
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-sm font-medium text-buddy-text-primary">
        {label}
      </label>
      <textarea
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        rows={3}
        placeholder={placeholder}
        className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm text-buddy-text-primary placeholder:text-buddy-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-buddy-primary disabled:opacity-60"
      />
    </div>
  );
}

function SaveStatus({ state, onRetry }: { state: SaveState; onRetry: () => void }) {
  if (state === "idle") return <div className="h-4" aria-hidden="true" />;

  return (
    <p aria-live="polite" className="flex items-center gap-2 text-xs text-buddy-muted">
      {state === "saving" && "Saving…"}
      {state === "saved" && "Saved"}
      {state === "error" && (
        <span role="alert" className="flex items-center gap-2 text-red-600">
          Save failed
          <button
            type="button"
            onClick={onRetry}
            className="font-medium underline underline-offset-2 hover:text-red-700"
          >
            Retry
          </button>
        </span>
      )}
    </p>
  );
}

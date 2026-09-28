"use client";

import clsx from "clsx";

interface FindingsFormProps {
  serviceOptions: string[];
  causeOptions: string[];
  affectedService: string;
  likelyCause: string;
  reasoning: string;
  onServiceChange: (service: string) => void;
  onCauseChange: (cause: string) => void;
  onReasoningChange: (reasoning: string) => void;
  onReasoningBlur: () => void;
  disabled?: boolean;
}

/**
 * Deliberately no correctness styling anywhere in this form — the employee
 * gets no visual hint about which option is right until after submission.
 */
export function FindingsForm({
  serviceOptions,
  causeOptions,
  affectedService,
  likelyCause,
  reasoning,
  onServiceChange,
  onCauseChange,
  onReasoningChange,
  onReasoningBlur,
  disabled,
}: FindingsFormProps) {
  return (
    <div className="space-y-6">
      <OptionGroup
        legend="Which service is affected?"
        name="affected-service"
        options={serviceOptions}
        value={affectedService}
        onChange={onServiceChange}
        disabled={disabled}
      />

      <OptionGroup
        legend="What's the likely cause?"
        name="likely-cause"
        options={causeOptions}
        value={likelyCause}
        onChange={onCauseChange}
        disabled={disabled}
      />

      <div>
        <label htmlFor="mission-reasoning" className="mb-2 block text-sm font-medium text-buddy-text-primary">
          Explain your reasoning
        </label>
        <textarea
          id="mission-reasoning"
          value={reasoning}
          onChange={(e) => onReasoningChange(e.target.value)}
          onBlur={onReasoningBlur}
          disabled={disabled}
          rows={4}
          placeholder="What evidence led you to this conclusion?"
          className="w-full rounded-lg border border-buddy-border bg-buddy-surface px-3 py-2 text-sm text-buddy-text-primary placeholder:text-buddy-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-buddy-primary disabled:opacity-60"
        />
      </div>
    </div>
  );
}

function OptionGroup({
  legend,
  name,
  options,
  value,
  onChange,
  disabled,
}: {
  legend: string;
  name: string;
  options: string[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-medium text-buddy-text-primary">{legend}</legend>
      <div className="space-y-2">
        {options.map((option) => (
          <label
            key={option}
            className={clsx(
              "flex cursor-pointer items-center gap-3 rounded-lg border border-buddy-border px-3 py-2 text-sm transition-colors",
              value === option
                ? "border-buddy-primary bg-buddy-primary/5"
                : "hover:border-buddy-primary/40",
              disabled && "cursor-not-allowed opacity-60"
            )}
          >
            <input
              type="radio"
              name={name}
              value={option}
              checked={value === option}
              onChange={() => onChange(option)}
              disabled={disabled}
              className="accent-[var(--buddy-primary)]"
            />
            {option}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

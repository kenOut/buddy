"use client";

import { useEffect, useRef, useState } from "react";

import { SlideUp } from "@/components/animations/SlideUp";
import { ProgressAnimation } from "@/components/animations/ProgressAnimation";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ApiError } from "@/lib/api";
import { submitMissionAttempt, updateMissionAttempt } from "@/lib/missionAttempts";
import type { MissionAssignment, MissionAttempt, MissionScenario } from "@/lib/types";
import { CapabilityInsight } from "./CapabilityInsight";
import { EvidencePanel, evidenceKeysFor, type EvidenceCategory } from "./EvidencePanel";
import { FindingsForm } from "./FindingsForm";
import { MissionBuddy, type MissionBuddyPhase } from "./MissionBuddy";

interface InvestigationWorkspaceProps {
  assignment: MissionAssignment;
  scenario: MissionScenario;
  attempt: MissionAttempt;
  employeeId: string;
  onSubmitted: (attempt: MissionAttempt) => void;
}

export function InvestigationWorkspace({
  assignment,
  scenario,
  attempt: initialAttempt,
  employeeId,
  onSubmitted,
}: InvestigationWorkspaceProps) {
  // The single source of truth for this attempt's persisted state — replaced
  // wholesale by whatever the server returns from an update or a submit, so
  // the UI can never drift from what's actually saved.
  const [attempt, setAttempt] = useState(initialAttempt);

  const [activeTab, setActiveTab] = useState<EvidenceCategory>("metrics");
  const [viewed, setViewed] = useState<Set<string>>(
    () => new Set([...initialAttempt.evidence_viewed, ...evidenceKeysFor(scenario, "metrics")])
  );
  const [affectedService, setAffectedService] = useState(initialAttempt.affected_service ?? "");
  const [likelyCause, setLikelyCause] = useState(initialAttempt.likely_cause ?? "");
  const [reasoning, setReasoning] = useState(initialAttempt.reasoning ?? "");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const submittingRef = useRef(false);
  const [hasInteracted, setHasInteracted] = useState(false);

  // Persists the default tab's evidence as viewed if it wasn't already
  // recorded (e.g. this is the first time opening the mission). No local
  // setState here — `viewed` above is already correct from initial render.
  useEffect(() => {
    const keys = Array.from(viewed);
    const alreadySaved =
      initialAttempt.evidence_viewed.length === keys.length &&
      keys.every((k) => initialAttempt.evidence_viewed.includes(k));
    if (!alreadySaved) {
      updateMissionAttempt(initialAttempt.id, { evidence_viewed: keys }).catch(() => {
        setSaveError("Couldn't save your progress. It'll retry as you keep investigating.");
      });
    }
    // Intentionally run once on mount — this seeds persistence for the
    // pre-opened default tab only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isReadOnly = attempt.status === "completed";
  const hasResult = attempt.score != null;
  const canSubmit = !!affectedService && !!likelyCause && reasoning.trim().length > 0;

  const buddyPhase: MissionBuddyPhase = hasResult
    ? attempt.passed
      ? "success"
      : "encouraging"
    : submitting
      ? "submitting"
      : hasInteracted
        ? "investigating"
        : "opening";

  const openTab = (tab: EvidenceCategory) => {
    setHasInteracted(true);
    setActiveTab(tab);
    const keys = evidenceKeysFor(scenario, tab);
    const alreadyViewed = keys.every((k) => viewed.has(k));
    if (alreadyViewed) return;

    const merged = new Set(viewed);
    keys.forEach((k) => merged.add(k));
    setViewed(merged);
    setSaveError(null);
    updateMissionAttempt(attempt.id, { evidence_viewed: Array.from(merged) }).catch(() => {
      setSaveError("Couldn't save your progress. It'll retry as you keep investigating.");
    });
  };

  const selectService = (service: string) => {
    setHasInteracted(true);
    setAffectedService(service);
    setSaveError(null);
    updateMissionAttempt(attempt.id, { affected_service: service }).catch(() => {
      setSaveError("Couldn't save your selection. It'll retry the next time you change something.");
    });
  };

  const selectCause = (cause: string) => {
    setHasInteracted(true);
    setLikelyCause(cause);
    setSaveError(null);
    updateMissionAttempt(attempt.id, { likely_cause: cause }).catch(() => {
      setSaveError("Couldn't save your selection. It'll retry the next time you change something.");
    });
  };

  const changeReasoning = (value: string) => {
    setHasInteracted(true);
    setReasoning(value);
  };

  const saveReasoning = () => {
    updateMissionAttempt(attempt.id, { reasoning }).catch(() => {
      setSaveError("Couldn't save your reasoning. It'll retry the next time you change something.");
    });
  };

  // Explicit retry, rather than only relying on the next interaction to
  // silently retry — resends everything currently on screen in one call,
  // so it's correct regardless of which specific field failed to save.
  const retrySave = () => {
    setSaveError(null);
    updateMissionAttempt(attempt.id, {
      affected_service: affectedService || undefined,
      likely_cause: likelyCause || undefined,
      reasoning: reasoning || undefined,
      evidence_viewed: Array.from(viewed),
    }).catch(() => {
      setSaveError("Still couldn't save. Check your connection and try again.");
    });
  };

  const submit = async () => {
    // A ref-based guard, not just `disabled={submitting}` on the button —
    // `submitting` state only updates on the next render, which leaves a
    // window for two near-simultaneous clicks to both pass the check before
    // React re-renders the disabled button. The ref updates synchronously,
    // so the second call is rejected immediately, in the same tick.
    if (submittingRef.current || !canSubmit) return;
    submittingRef.current = true;

    setSubmitting(true);
    setSubmitError(null);
    try {
      const result = await submitMissionAttempt(attempt.id, {
        employee_id: employeeId,
        affected_service: affectedService,
        likely_cause: likelyCause,
        reasoning,
        evidence_viewed: Array.from(viewed),
      });
      setAttempt(result);
      onSubmitted(result);
    } catch (err) {
      setSubmitError(
        err instanceof ApiError
          ? "Couldn't submit your investigation. Please try again."
          : "Network error — couldn't reach the server. Please try again."
      );
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="font-heading text-xl font-bold text-buddy-navy sm:text-2xl">
          {assignment.mission.title}
        </h1>
        <div className="flex items-center gap-2">
          {assignment.mission.required && <Badge tone="coral">Required for readiness</Badge>}
          <Badge tone={attempt.status === "completed" ? "success" : "info"}>
            {attempt.status.replace("_", " ")}
          </Badge>
        </div>
      </div>

      <MissionBuddy phase={buddyPhase} />

      <Card>
        <p className="text-xs font-semibold uppercase tracking-wide text-buddy-primary">Scenario</p>
        <p className="mt-2 text-sm text-buddy-text-primary">{scenario.briefing}</p>
      </Card>

      <div aria-live="polite">{hasResult && <ResultCard attempt={attempt} />}</div>

      {hasResult && attempt.passed && (
        <CapabilityInsight attemptId={attempt.id} employeeId={employeeId} />
      )}

      {/* Single column on mobile (DOM order = Evidence, then Findings, then
          Submit, matching the requested mobile stack). On large screens,
          Evidence and Findings sit side by side like a real investigation
          desk — reference material on the left, your conclusion on the
          right. */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5 lg:items-start">
        <Card className="lg:col-span-3">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-buddy-muted">
            Evidence
          </p>
          <EvidencePanel
            scenario={scenario}
            activeTab={activeTab}
            onOpenTab={openTab}
            viewedKeys={viewed}
          />
        </Card>

        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-buddy-muted">
              Your findings
            </p>
            <FindingsForm
              serviceOptions={scenario.service_options}
              causeOptions={scenario.cause_options}
              affectedService={affectedService}
              likelyCause={likelyCause}
              reasoning={reasoning}
              onServiceChange={selectService}
              onCauseChange={selectCause}
              onReasoningChange={changeReasoning}
              onReasoningBlur={saveReasoning}
              disabled={isReadOnly}
            />
          </Card>

          {saveError && (
            <div role="alert" className="flex items-center justify-between gap-3 text-sm text-red-600">
              <span>{saveError}</span>
              <button
                type="button"
                onClick={retrySave}
                className="shrink-0 font-medium underline underline-offset-2 hover:text-red-700"
              >
                Retry
              </button>
            </div>
          )}

          {!isReadOnly && (
            <Card>
              {submitError && (
                <p role="alert" className="mb-3 text-sm text-red-600">
                  {submitError}
                </p>
              )}
              <Button onClick={submit} disabled={!canSubmit || submitting} className="w-full">
                {submitting ? "Submitting…" : hasResult ? "Resubmit investigation" : "Submit investigation"}
              </Button>
              {!canSubmit && (
                <p className="mt-2 text-center text-xs text-buddy-muted">
                  Select a service, a likely cause, and explain your reasoning to submit.
                </p>
              )}
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function ResultCard({ attempt }: { attempt: MissionAttempt }) {
  return (
    <SlideUp duration={0.35}>
      <Card className={attempt.passed ? "border-buddy-aurora/40 bg-buddy-aurora/5" : undefined}>
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-buddy-muted">
            {attempt.passed ? "Investigation complete" : "Last submission"}
          </p>
          <p className="font-heading text-2xl font-bold text-buddy-navy">{attempt.score}%</p>
        </div>
        <ProgressAnimation percent={attempt.score ?? 0} height={6} className="mt-3" />
        {attempt.feedback && (
          <p className="mt-3 text-sm text-buddy-text-primary">{attempt.feedback}</p>
        )}
      </Card>
    </SlideUp>
  );
}

import type { QuestEvidenceItem } from "@/lib/types";

/**
 * Phase 7 Stage 3 — the Troubleshooting Workspace's own structured state,
 * and the boundary that keeps the existing evaluation pipeline working
 * without it ever reading this shape.
 *
 * Every field here is JSON-safe (string / string[] / nested object of the
 * same) — no Set, Date, or class instance — because this is exactly what
 * gets written to `QuestAttempt.submission.workspace.payload` verbatim.
 */
export interface Hypothesis {
  id: string;
  statement: string;
  reasoning: string;
  supporting_evidence_ids: string[];
}

export interface TroubleshootDiagnosis {
  root_cause: string;
  confidence: string | null;
}

export interface TroubleshootResolution {
  proposed_fix: string;
  validation_plan: string | null;
}

export interface TroubleshootPayload {
  observations: string[];
  evidence_reviewed: string[];
  hypotheses: Hypothesis[];
  diagnosis: TroubleshootDiagnosis;
  resolution: TroubleshootResolution;
}

export const EMPTY_TROUBLESHOOT_PAYLOAD: TroubleshootPayload = {
  observations: [],
  evidence_reviewed: [],
  hypotheses: [],
  diagnosis: { root_cause: "", confidence: null },
  resolution: { proposed_fix: "", validation_plan: null },
};

/** The slice of QuestEvidenceItem the adapter needs to turn evidence ids
 * into readable titles when synthesizing legacy prose — never the full
 * item (no content, no description leaks into the synthesized text). */
export type EvidenceRef = Pick<QuestEvidenceItem, "id" | "title" | "evidence_type">;

export function evidenceRefsFromQuest(evidence: QuestEvidenceItem[]): EvidenceRef[] {
  return evidence.map((e) => ({ id: e.id, title: e.title, evidence_type: e.evidence_type }));
}

// =====================================================================
// fromSubmission — raw JSON -> structured state, never throws
// =====================================================================

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((v): v is string => typeof v === "string");
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asNullableString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function asHypothesis(value: unknown, fallbackIndex: number): Hypothesis | null {
  if (typeof value !== "object" || value === null) return null;
  const v = value as Record<string, unknown>;
  const statement = asString(v.statement);
  const reasoning = asString(v.reasoning);
  const supporting = asStringArray(v.supporting_evidence_ids);
  if (!statement && !reasoning && supporting.length === 0) return null;
  return {
    id: typeof v.id === "string" && v.id ? v.id : `restored-${fallbackIndex}`,
    statement,
    reasoning,
    supporting_evidence_ids: supporting,
  };
}

function asHypotheses(value: unknown): Hypothesis[] {
  if (!Array.isArray(value)) return [];
  const out: Hypothesis[] = [];
  value.forEach((item, i) => {
    const h = asHypothesis(item, i);
    if (h) out.push(h);
  });
  return out;
}

function asDiagnosis(value: unknown): TroubleshootDiagnosis {
  if (typeof value !== "object" || value === null) return { ...EMPTY_TROUBLESHOOT_PAYLOAD.diagnosis };
  const v = value as Record<string, unknown>;
  return { root_cause: asString(v.root_cause), confidence: asNullableString(v.confidence) };
}

function asResolution(value: unknown): TroubleshootResolution {
  if (typeof value !== "object" || value === null) return { ...EMPTY_TROUBLESHOOT_PAYLOAD.resolution };
  const v = value as Record<string, unknown>;
  return {
    proposed_fix: asString(v.proposed_fix),
    validation_plan: asNullableString(v.validation_plan),
  };
}

/**
 * Reconstructs structured Troubleshoot state from whatever is currently
 * stored at `attempt.submission.workspace.payload` (already extracted by
 * useWorkspaceEngine into `draft.workspacePayload` before this is called
 * — this function never touches `attempt.submission` directly).
 *
 * Handles every case Stage 2/3 called out, none of them by throwing:
 *   - new attempt (payload is null/undefined)        -> EMPTY_TROUBLESHOOT_PAYLOAD
 *   - partial payload (some fields missing)           -> those fields default individually
 *   - legacy attempt (no workspace payload at all)     -> same as "new attempt"
 *   - malformed payload (wrong types, garbage shapes)  -> each field defaults independently,
 *                                                          never crashes the whole workspace
 *   - a complete prior Troubleshoot payload            -> restored exactly
 */
export function fromSubmission(rawPayload: unknown): TroubleshootPayload {
  if (typeof rawPayload !== "object" || rawPayload === null) {
    return { ...EMPTY_TROUBLESHOOT_PAYLOAD, diagnosis: { ...EMPTY_TROUBLESHOOT_PAYLOAD.diagnosis }, resolution: { ...EMPTY_TROUBLESHOOT_PAYLOAD.resolution } };
  }
  const v = rawPayload as Record<string, unknown>;
  return {
    observations: asStringArray(v.observations),
    evidence_reviewed: asStringArray(v.evidence_reviewed),
    hypotheses: asHypotheses(v.hypotheses),
    diagnosis: asDiagnosis(v.diagnosis),
    resolution: asResolution(v.resolution),
  };
}

// =====================================================================
// toSubmission — structured state -> deterministic legacy prose
// =====================================================================

function uniqueTitles(ids: string[], byId: Map<string, EvidenceRef>): string[] {
  const seen = new Set<string>();
  const titles: string[] = [];
  for (const id of ids) {
    const ref = byId.get(id);
    if (!ref || seen.has(ref.title)) continue;
    seen.add(ref.title);
    titles.push(ref.title);
  }
  return titles;
}

function buildFindings(payload: TroubleshootPayload, byId: Map<string, EvidenceRef>): string {
  const lines: string[] = [];
  const titles = uniqueTitles(payload.evidence_reviewed, byId);
  if (titles.length > 0) {
    lines.push(
      `Reviewed ${titles.length} evidence source${titles.length === 1 ? "" : "s"}: ${titles.join(", ")}.`
    );
  } else {
    lines.push("No evidence marked as reviewed yet.");
  }
  if (payload.observations.length > 0) {
    lines.push(`Observations: ${payload.observations.join("; ")}`);
  }
  return lines.join("\n");
}

function buildReasoning(payload: TroubleshootPayload, byId: Map<string, EvidenceRef>): string {
  const blocks: string[] = [];
  payload.hypotheses.forEach((h, i) => {
    if (!h.statement && !h.reasoning) return;
    const lines = [`Hypothesis ${i + 1}: ${h.statement || "(no statement recorded)"}`];
    if (h.reasoning) lines.push(`Reasoning: ${h.reasoning}`);
    const supportTitles = uniqueTitles(h.supporting_evidence_ids, byId);
    if (supportTitles.length > 0) lines.push(`Supported by: ${supportTitles.join(", ")}`);
    blocks.push(lines.join("\n"));
  });
  if (payload.diagnosis.root_cause) {
    const confidence = payload.diagnosis.confidence ? ` (confidence: ${payload.diagnosis.confidence})` : "";
    blocks.push(`Diagnosis: ${payload.diagnosis.root_cause}${confidence}`);
  }
  return blocks.join("\n\n");
}

function buildSolution(payload: TroubleshootPayload): string {
  const blocks: string[] = [];
  if (payload.resolution.proposed_fix) {
    blocks.push(`Proposed resolution: ${payload.resolution.proposed_fix}`);
  }
  if (payload.resolution.validation_plan) {
    blocks.push(`Validation plan: ${payload.resolution.validation_plan}`);
  }
  return blocks.join("\n\n");
}

export interface LegacySubmissionFields {
  findings: string;
  reasoning: string;
  solution: string;
}

/**
 * Deterministically synthesizes the legacy findings/reasoning/solution
 * strings the existing evaluator reads (evaluate_deterministic,
 * QuestAIEvaluationContext — both confirmed in the Stage 2 report to read
 * exactly these three fields and nothing else) from the structured
 * Troubleshoot payload.
 *
 * No AI, no randomness, no SRE-specific wording — every sentence is
 * mechanically assembled from fields the employee actually filled in.
 * Never invents facts: an empty section produces an honest "not yet"
 * line (findings) or simply contributes nothing (reasoning/solution),
 * never a fabricated placeholder presented as real content.
 */
export function toSubmission(payload: TroubleshootPayload, evidence: EvidenceRef[]): LegacySubmissionFields {
  const byId = new Map(evidence.map((e) => [e.id, e]));
  return {
    findings: buildFindings(payload, byId),
    reasoning: buildReasoning(payload, byId),
    solution: buildSolution(payload),
  };
}

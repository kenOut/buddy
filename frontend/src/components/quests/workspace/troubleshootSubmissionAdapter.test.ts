// Phase 7 Stage 3 — isolated unit tests for the Troubleshoot submission
// adapter, run with Node's built-in test runner (no new devDependency):
//
//   node --test src/components/quests/workspace/troubleshootSubmissionAdapter.test.ts
//
// Deliberately framework-free: this repo has no frontend unit test runner
// installed anywhere else, and node:test/node:assert cover everything an
// adapter this small needs.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  EMPTY_TROUBLESHOOT_PAYLOAD,
  fromSubmission,
  toSubmission,
  type EvidenceRef,
  type TroubleshootPayload,
} from "./troubleshootSubmissionAdapter.ts";

const EVIDENCE: EvidenceRef[] = [
  { id: "ev-1", title: "Error rate graph", evidence_type: "METRICS" },
  { id: "ev-2", title: "Recent deploy log", evidence_type: "LOGS" },
];

// ---- fromSubmission: case A — new attempt ----

test("fromSubmission: undefined payload returns empty defaults", () => {
  const result = fromSubmission(undefined);
  assert.deepEqual(result, EMPTY_TROUBLESHOOT_PAYLOAD);
});

test("fromSubmission: null payload returns empty defaults", () => {
  const result = fromSubmission(null);
  assert.deepEqual(result, EMPTY_TROUBLESHOOT_PAYLOAD);
});

// ---- fromSubmission: case C — legacy attempt, no workspace payload ----

test("fromSubmission: legacy attempt (no troubleshoot payload at all) does not crash", () => {
  // Simulates what draft.workspacePayload is for an attempt that only
  // ever had findings/reasoning/solution — useWorkspaceEngine passes
  // `undefined` through in that case.
  const result = fromSubmission(undefined);
  assert.deepEqual(result, EMPTY_TROUBLESHOOT_PAYLOAD);
});

// ---- fromSubmission: case B — partial state ----

test("fromSubmission: partial payload restores only what exists", () => {
  const result = fromSubmission({ observations: ["saw a spike"] });
  assert.deepEqual(result.observations, ["saw a spike"]);
  assert.deepEqual(result.evidence_reviewed, []);
  assert.deepEqual(result.hypotheses, []);
  assert.equal(result.diagnosis.root_cause, "");
  assert.equal(result.resolution.proposed_fix, "");
});

// ---- fromSubmission: case D — malformed payload ----

test("fromSubmission: malformed payload (wrong types) falls back to safe defaults per field", () => {
  const result = fromSubmission({
    observations: "not an array",
    evidence_reviewed: 42,
    hypotheses: "nope",
    diagnosis: "also nope",
    resolution: ["still nope"],
  });
  assert.deepEqual(result, EMPTY_TROUBLESHOOT_PAYLOAD);
});

test("fromSubmission: entirely non-object payload does not throw", () => {
  assert.doesNotThrow(() => fromSubmission("just a string"));
  assert.doesNotThrow(() => fromSubmission(12345));
  assert.doesNotThrow(() => fromSubmission(["array", "not", "object"]));
});

test("fromSubmission: hypothesis entries missing an id get a stable fallback id", () => {
  const result = fromSubmission({
    hypotheses: [{ statement: "deploy caused it", reasoning: "timing lines up", supporting_evidence_ids: ["ev-2"] }],
  });
  assert.equal(result.hypotheses.length, 1);
  assert.equal(typeof result.hypotheses[0].id, "string");
  assert.ok(result.hypotheses[0].id.length > 0);
});

test("fromSubmission: malformed individual hypothesis entries are dropped, not fatal", () => {
  const result = fromSubmission({
    hypotheses: [null, "garbage", 42, { statement: "real one", reasoning: "", supporting_evidence_ids: [] }],
  });
  assert.equal(result.hypotheses.length, 1);
  assert.equal(result.hypotheses[0].statement, "real one");
});

// ---- fromSubmission: case E — complete round trip ----

test("round trip: complete state survives toSubmission -> fromSubmission unchanged", () => {
  const original: TroubleshootPayload = {
    observations: ["latency climbing since 14:00"],
    evidence_reviewed: ["ev-1", "ev-2"],
    hypotheses: [
      {
        id: "h1",
        statement: "The 14:00 deploy introduced a regression",
        reasoning: "Timing matches exactly",
        supporting_evidence_ids: ["ev-2"],
      },
    ],
    diagnosis: { root_cause: "Deploy at 14:00 regressed the checkout path", confidence: "High" },
    resolution: { proposed_fix: "Roll back the deploy", validation_plan: "Confirm error rate returns to baseline" },
  };

  // fromSubmission is only ever called on the raw JSON that was actually
  // persisted — round trip here means: reconstruct from a plain-JSON
  // clone (as if it came back from the API), same as production.
  const persisted = JSON.parse(JSON.stringify(original));
  const restored = fromSubmission(persisted);
  assert.deepEqual(restored, original);
});

// ---- toSubmission: legacy field synthesis ----

test("toSubmission: empty payload produces an honest 'not yet' findings line and empty reasoning/solution", () => {
  const result = toSubmission(EMPTY_TROUBLESHOOT_PAYLOAD, EVIDENCE);
  assert.equal(result.findings, "No evidence marked as reviewed yet.");
  assert.equal(result.reasoning, "");
  assert.equal(result.solution, "");
});

test("toSubmission: findings reflects reviewed evidence titles and observations", () => {
  const payload: TroubleshootPayload = {
    ...EMPTY_TROUBLESHOOT_PAYLOAD,
    evidence_reviewed: ["ev-1", "ev-2"],
    observations: ["error rate doubled"],
  };
  const result = toSubmission(payload, EVIDENCE);
  assert.match(result.findings, /Reviewed 2 evidence sources: Error rate graph, Recent deploy log\./);
  assert.match(result.findings, /Observations: error rate doubled/);
});

test("toSubmission: findings deduplicates repeated evidence ids by title", () => {
  const payload: TroubleshootPayload = { ...EMPTY_TROUBLESHOOT_PAYLOAD, evidence_reviewed: ["ev-1", "ev-1"] };
  const result = toSubmission(payload, EVIDENCE);
  assert.match(result.findings, /Reviewed 1 evidence source: Error rate graph\./);
});

test("toSubmission: reasoning includes every hypothesis plus supporting evidence titles", () => {
  const payload: TroubleshootPayload = {
    ...EMPTY_TROUBLESHOOT_PAYLOAD,
    hypotheses: [
      { id: "h1", statement: "Deploy regression", reasoning: "Timing lines up", supporting_evidence_ids: ["ev-2"] },
      { id: "h2", statement: "Traffic spike", reasoning: "", supporting_evidence_ids: [] },
    ],
  };
  const result = toSubmission(payload, EVIDENCE);
  assert.match(result.reasoning, /Hypothesis 1: Deploy regression/);
  assert.match(result.reasoning, /Reasoning: Timing lines up/);
  assert.match(result.reasoning, /Supported by: Recent deploy log/);
  assert.match(result.reasoning, /Hypothesis 2: Traffic spike/);
});

test("toSubmission: reasoning appends diagnosis with stated confidence", () => {
  const payload: TroubleshootPayload = {
    ...EMPTY_TROUBLESHOOT_PAYLOAD,
    diagnosis: { root_cause: "Bad deploy", confidence: "Medium" },
  };
  const result = toSubmission(payload, EVIDENCE);
  assert.match(result.reasoning, /Diagnosis: Bad deploy \(confidence: Medium\)/);
});

test("toSubmission: solution reflects proposed_fix and optional validation_plan", () => {
  const payload: TroubleshootPayload = {
    ...EMPTY_TROUBLESHOOT_PAYLOAD,
    resolution: { proposed_fix: "Roll back", validation_plan: "Watch error rate for 10 minutes" },
  };
  const result = toSubmission(payload, EVIDENCE);
  assert.match(result.solution, /Proposed resolution: Roll back/);
  assert.match(result.solution, /Validation plan: Watch error rate for 10 minutes/);
});

test("toSubmission: solution omits validation plan line when null", () => {
  const payload: TroubleshootPayload = { ...EMPTY_TROUBLESHOOT_PAYLOAD, resolution: { proposed_fix: "Roll back", validation_plan: null } };
  const result = toSubmission(payload, EVIDENCE);
  assert.equal(result.solution, "Proposed resolution: Roll back");
});

test("toSubmission: never fabricates content for fields the employee left empty", () => {
  const payload: TroubleshootPayload = {
    ...EMPTY_TROUBLESHOOT_PAYLOAD,
    hypotheses: [{ id: "h1", statement: "", reasoning: "", supporting_evidence_ids: [] }],
  };
  const result = toSubmission(payload, EVIDENCE);
  // An entirely-empty hypothesis contributes nothing rather than a fake "(no statement)" line.
  assert.equal(result.reasoning, "");
});

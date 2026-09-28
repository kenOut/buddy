"""The AI provider boundary.

`AIProvider` is the interface every provider (mock or real) implements.
It returns a *raw string* only — parsing and Pydantic validation happen
one layer up, in ai_evaluation_service.py, never inside a provider. That
keeps "did the AI say something we can trust" a single, provider-agnostic
question.

No real provider is wired up here: no credentials exist in this project,
and none are invented. `MockAIProvider` is a deterministic, rule-based
stand-in — genuinely code-derived from the evaluation context (not a
single canned string), so local dev and tests exercise real branching
logic without ever calling out to the network. Swapping in a real
provider later means implementing this same Protocol and changing
`settings.ai_provider` — nothing in ai_evaluation_service.py has to change.
"""

import json
from dataclasses import dataclass
from typing import Protocol

from app.services.evaluation_context import TroubleshootWorkspaceContext


@dataclass
class AIEvaluationContext:
    """Exactly what the AI is allowed to see — evidence that actually
    exists, nothing more. No hidden answer key (mission_scenarios.py's
    `correct_service`/`correct_cause` never appear here), and the AI is
    never asked to re-grade objective correctness — `objective_passed`/
    `objective_score` are handed to it as already-decided facts to
    interpret, not questions to answer."""

    employee_job_title: str | None
    mission_title: str
    mission_briefing: str
    affected_service: str
    likely_cause: str
    reasoning: str
    evidence_viewed: list[str]
    objective_passed: bool
    objective_score: float


@dataclass
class QuestDeterministicCriterionResult:
    """One deterministically-evaluated QuestEvaluationCriterion's outcome,
    handed to the AI as an already-decided fact — never a question for it
    to re-grade (same trust boundary as Mission's objective_passed)."""

    name: str
    passed: bool
    evidence: str


@dataclass
class QuestAIEvaluationContext:
    """The Quest equivalent of AIEvaluationContext — deliberately a
    separate shape rather than forcing Quest data into Mission's
    affected_service/likely_cause/mission_title fields, which don't mean
    anything for a BUILD or DESIGN quest. Built from exactly what Stage 4/5
    actually have: no hidden reference_solution/expected_answer text is
    included, only the pass/fail facts already decided by deterministic
    evaluation (see quest_evaluation_service.py)."""

    employee_job_title: str | None
    quest_title: str
    quest_description: str
    quest_type: str
    task_titles_completed: list[str]
    task_titles_skipped: list[str]
    findings: str
    reasoning: str
    solution: str
    deterministic_results: list[QuestDeterministicCriterionResult]
    qualitative_criterion_descriptions: list[str]
    target_capability_keys: list[str]
    objective_passed: bool
    objective_score: float
    # Phase 7 Stage 4D — additive. `None` for GENERAL and for any
    # TROUBLESHOOT attempt with no structured payload (legacy-only) —
    # both preserve pre-Stage-4D behavior exactly, since every branch
    # below that reads this field only ever runs when it's not None.
    # Reuses evaluation_context.py's TroubleshootWorkspaceContext
    # directly rather than duplicating its shape or its parsing —
    # whatever Stage 4B/4C already reconstructed server-side from
    # `submission.workspace.payload` is exactly what the AI sees here,
    # nothing re-derived and nothing invented. Structurally incapable of
    # carrying expected_answer/expected_behavior/reference_solution/
    # max_score — that type has no such field, by construction, same
    # discipline the rest of this dataclass already follows.
    troubleshoot: TroubleshootWorkspaceContext | None = None


class AIProviderError(Exception):
    """Raised by a provider when it cannot produce a response at all
    (unavailable, timed out, etc.) — distinct from a response that came
    back but failed validation, which is handled by the caller."""


class AIProvider(Protocol):
    model_name: str

    async def generate(self, context: AIEvaluationContext) -> str:
        """Returns raw text expected to be JSON matching AIEvaluationResponse.
        May raise AIProviderError if no response could be produced."""
        ...

    async def generate_for_quest(self, context: QuestAIEvaluationContext) -> str:
        """The Quest-domain equivalent of generate() — same output
        contract (raw JSON matching AIEvaluationResponse), same
        AIProviderError-on-unavailable behavior. A separate method on the
        same provider/Protocol, not a second competing provider
        architecture: one AIProvider implementation serves both Mission
        and Quest evaluation."""
        ...


def _bucket_reasoning_quality(reasoning: str) -> tuple[str, float]:
    """A deterministic proxy for explanation quality, standing in for what
    a real LLM would actually judge. Length is a crude signal on its own —
    this only exists so the mock provider's behavior is explainable and
    reproducible, not a claim that length equals quality."""
    length = len(reasoning.strip())
    if length >= 120:
        return "STRONG", 0.8
    if length >= 40:
        return "CAPABLE", 0.65
    return "DEVELOPING", 0.45


def _bucket_investigation_breadth(evidence_viewed: list[str]) -> tuple[str, float]:
    categories = {v.split(":", 1)[0] for v in evidence_viewed if ":" in v}
    if len(categories) >= 3:
        return "STRONG", 0.75
    if len(categories) >= 2:
        return "CAPABLE", 0.6
    return "DEVELOPING", 0.4


class MockAIProvider:
    """Deterministic local/dev/test provider — no network, no credentials,
    always available. Reasons over the same context a real provider would
    receive, using simple documented rules instead of a model."""

    model_name = "mock-heuristic-v1"

    async def generate(self, context: AIEvaluationContext) -> str:
        # An empty affected_service is this context's signal that the
        # mission had no investigation to diagnose (a reflection-workspace
        # mission — see ai_evaluation_service._build_context) rather than
        # a real investigation the employee simply didn't fill in;
        # missing/blank required fields on an actual investigation attempt
        # can't reach this provider at all (mission_scenarios.grade
        # requires them for `objective_passed` to even be computed).
        if not context.affected_service:
            return self._generate_for_reflection(context)

        strengths: list[str] = []
        development_areas: list[str] = []
        capabilities: list[dict] = []

        if context.objective_passed:
            strengths.append(
                f"Correctly identified {context.affected_service} and traced it to the right cause."
            )
        else:
            development_areas.append(
                "The conclusion didn't quite match what the evidence showed — worth revisiting."
            )

        breadth_level, breadth_confidence = _bucket_investigation_breadth(context.evidence_viewed)
        if breadth_level in ("CAPABLE", "STRONG"):
            strengths.append("Checked more than one evidence source before concluding.")
        else:
            development_areas.append("Try checking a wider range of evidence before concluding next time.")

        capabilities.append(
            {
                "capability": "troubleshooting",
                "level": breadth_level,
                "confidence": breadth_confidence,
                "evidence": "Breadth of evidence reviewed before reaching a conclusion.",
            }
        )

        reasoning_level, reasoning_confidence = _bucket_reasoning_quality(context.reasoning)
        if reasoning_level == "DEVELOPING":
            development_areas.append(
                "The investigation was sound, but the explanation could be more structured and detailed."
            )
        else:
            strengths.append("Explained the reasoning clearly enough for someone else to follow.")

        capabilities.append(
            {
                "capability": "documentation",
                "level": reasoning_level,
                "confidence": reasoning_confidence,
                "evidence": "Clarity and completeness of the written explanation.",
            }
        )

        weakest = min(capabilities, key=lambda c: c["confidence"])
        recommended_focus = (
            f"Another mission that exercises {weakest['capability'].replace('_', ' ')} "
            "would help build on this."
        )

        summary = (
            "This investigation reached the right conclusion and showed real signal-following."
            if context.objective_passed
            else "This investigation didn't land on the right conclusion, but the approach has real building blocks."
        )

        payload = {
            "summary": summary,
            "strengths": strengths or ["Completed the investigation."],
            "development_areas": development_areas,
            "capabilities": capabilities,
            "recommended_focus": recommended_focus,
        }
        return json.dumps(payload)

    def _generate_for_reflection(self, context: AIEvaluationContext) -> str:
        """A reflection-workspace mission has no objectively correct
        answer to grade — `context.objective_passed` here only means "the
        submission cleared the real-effort length bar" (see
        mission_attempt_service._grade_reflection), never "was right."
        So this reads only what a freeform submission can honestly
        support: how substantively it's written, mapped to the same
        communication/documentation/independence capabilities
        capability_evidence_pipeline's deterministic layer already uses
        for this same reasoning text — never troubleshooting, which has
        no basis here at all."""
        strengths: list[str] = []
        development_areas: list[str] = []

        reasoning_level, reasoning_confidence = _bucket_reasoning_quality(context.reasoning)
        if reasoning_level == "DEVELOPING":
            development_areas.append(
                "The submission covers the basics, but a bit more specificity about what was "
                "actually done would make it easier to build on."
            )
        else:
            strengths.append("Wrote a clear, specific account of what they actually did.")

        capabilities = [
            {
                "capability": "communication",
                "level": reasoning_level,
                "confidence": reasoning_confidence,
                "evidence": "Clarity and specificity of the written submission.",
            },
            {
                "capability": "independence",
                "level": "CAPABLE" if context.objective_passed else "DEVELOPING",
                "confidence": 0.5,
                "evidence": "Completed the mission and submitted real work without needing a follow-up.",
            },
        ]

        summary = (
            f'Completed "{context.mission_title}" and described the work in their own words.'
            if context.objective_passed
            else f'The submission for "{context.mission_title}" needs a bit more detail before it counts as done.'
        )

        payload = {
            "summary": summary,
            "strengths": strengths or ["Submitted real work for this mission."],
            "development_areas": development_areas,
            "capabilities": capabilities,
            "recommended_focus": "A mission with a more structured deliverable would help build on this.",
        }
        return json.dumps(payload)

    async def generate_for_quest(self, context: QuestAIEvaluationContext) -> str:
        """Deterministic, rule-based — same spirit as generate() above,
        adapted to what a Quest actually provides. Caller (
        quest_evaluation_service.py) must never call this with an empty
        target_capability_keys — AIEvaluationResponse requires at least
        one capability assessment, and there is nothing honest to assess
        if the quest maps to none.

        Phase 7 Stage 4D — the conceptual brief this function follows for
        the structured Troubleshoot case (`context.troubleshoot is not
        None`): evaluate the quality of the employee's submitted
        troubleshooting work; never determine objective correctness
        (that's `context.objective_passed`/`objective_score`, already
        decided by deterministic evaluation and never touched here);
        never invent facts — every observation below is derived only
        from a field that was actually present; and distinguish what was
        explicitly demonstrated (structural fact + reasoning-quality
        signal), what is missing (a required field left empty), from
        what plainly cannot be determined by a rule-based reader (never
        claimed). Domain-neutral throughout — nothing here reads
        `quest.title`/`quest.description` content to decide anything;
        the same code path runs regardless of what industry or
        problem domain a given quest happens to be about. Hypothesis
        *count* is deliberately never
        read as a signal, anywhere below — only presence/absence and
        whether a link to evidence exists — consistent with the hard
        rule established in Stage 3/4A/4B/4C that activity volume must
        never become evaluation input.
        """
        assert context.target_capability_keys, "generate_for_quest requires at least one target capability"

        strengths: list[str] = []
        development_areas: list[str] = []

        if context.objective_passed:
            strengths.append(f'Completed "{context.quest_title}" and satisfied the objective checks.')
        else:
            development_areas.append(
                "Some of the objective checks weren't satisfied — worth revisiting the evidence."
            )

        if context.task_titles_skipped:
            development_areas.append(
                f"{len(context.task_titles_skipped)} optional task(s) were left undone — "
                "not required, but worth considering next time."
            )

        reasoning_level, reasoning_confidence = _bucket_reasoning_quality(context.reasoning)
        solution_level, solution_confidence = _bucket_reasoning_quality(context.solution)

        if reasoning_level in ("CAPABLE", "STRONG"):
            strengths.append("Explained their reasoning clearly enough for someone else to follow.")
        else:
            development_areas.append("The reasoning could be more detailed and structured.")

        if solution_level in ("CAPABLE", "STRONG"):
            strengths.append("Proposed a concrete, specific solution.")
        else:
            development_areas.append("The proposed solution could be more concrete and specific.")

        # Structural signals derived from the structured Troubleshoot
        # payload, keyed by which capability they're a meaningful proxy
        # for. Empty unless `context.troubleshoot` is set (GENERAL and
        # legacy-only TROUBLESHOOT attempts leave this empty, so the
        # capability loop below falls through to the exact pre-Stage-4D
        # reasoning/solution round-robin, unchanged).
        structural_signals: dict[str, tuple[str, float, str]] = {}

        troubleshoot = context.troubleshoot
        if troubleshoot is not None:
            has_hypotheses = bool(troubleshoot.hypotheses)
            links_evidence = any(h.supporting_evidence_ids for h in troubleshoot.hypotheses)
            has_diagnosis = bool(troubleshoot.diagnosis.root_cause.strip())
            has_resolution = bool(troubleshoot.resolution.proposed_fix.strip())
            has_validation_plan = bool(troubleshoot.resolution.validation_plan)
            # `troubleshoot.evidence_reviewed` is deliberately not read
            # here at all, and no signal below is derived from its
            # length/count — Stage 4D's correction: evidence-review
            # breadth must never independently drive a capability level,
            # confidence, strength, or development-area note. The field
            # remains available on `context.troubleshoot` as context (an
            # AI provider could still mention *which* evidence the
            # employee says they reviewed), it just isn't a scoring input.

            if not has_diagnosis:
                development_areas.append("No diagnosis was recorded — nothing to evaluate for root-cause reasoning.")
            elif not has_hypotheses:
                development_areas.append("A diagnosis was reached without recording any hypotheses along the way.")
            elif not links_evidence:
                development_areas.append("The hypotheses weren't linked to any specific evidence reviewed.")
            else:
                strengths.append("Formed a hypothesis, linked it to supporting evidence, and reached a diagnosis.")

            if has_resolution and has_validation_plan:
                strengths.append("Proposed a resolution and described how to confirm it worked.")
            elif has_resolution:
                development_areas.append("A resolution was proposed without a way to confirm it worked.")
            else:
                development_areas.append("No resolution was proposed.")

            # Presence/linkage only — never a count — feeds these levels.
            if has_diagnosis and links_evidence:
                troubleshooting_level, troubleshooting_confidence = "STRONG", 0.8
            elif has_diagnosis or links_evidence:
                troubleshooting_level, troubleshooting_confidence = "CAPABLE", 0.6
            else:
                troubleshooting_level, troubleshooting_confidence = "DEVELOPING", 0.4
            structural_signals["troubleshooting"] = (
                troubleshooting_level,
                troubleshooting_confidence,
                "Assessed from whether a diagnosis was reached and supported by linked evidence.",
            )

            if has_hypotheses and links_evidence and has_diagnosis:
                problem_solving_level, problem_solving_confidence = "STRONG", 0.75
            elif has_hypotheses:
                problem_solving_level, problem_solving_confidence = "CAPABLE", 0.55
            else:
                problem_solving_level, problem_solving_confidence = "DEVELOPING", 0.4
            structural_signals["problem_solving"] = (
                problem_solving_level,
                problem_solving_confidence,
                "Assessed from whether hypotheses were formed and linked to supporting evidence before reaching a diagnosis.",
            )

        # No structural signal is registered for "independence" (or any
        # other capability not explicitly assigned above) — it falls
        # through to the same reasoning/solution round-robin every
        # capability used before this stage existed, per the correction
        # below.

        # Distribute the signals we actually have across whichever
        # capabilities this quest maps to — never inventing a signal for
        # a capability that wasn't actually observed. A failed objective
        # check caps the level at CAPABLE regardless of prose quality or
        # structural completeness: sounding thorough isn't a substitute
        # for being right, when rightness was checkable.
        capabilities: list[dict] = []
        for i, key in enumerate(context.target_capability_keys):
            if key in structural_signals:
                level, confidence, evidence_text = structural_signals[key]
            else:
                use_reasoning = i % 2 == 0
                level, confidence = (reasoning_level, reasoning_confidence) if use_reasoning else (solution_level, solution_confidence)
                evidence_text = (
                    f"Assessed from the quality and detail of the employee's "
                    f"{'reasoning' if use_reasoning else 'proposed solution'} on this quest."
                )
            if not context.objective_passed and level == "STRONG":
                level = "CAPABLE"
            capabilities.append(
                {
                    "capability": key,
                    "level": level,
                    "confidence": confidence,
                    "evidence": evidence_text,
                }
            )

        weakest = min(capabilities, key=lambda c: c["confidence"])
        recommended_focus = (
            f"Another quest that exercises {weakest['capability'].replace('_', ' ')} "
            "would help build on this."
        )

        summary = (
            f'"{context.quest_title}" was completed successfully, with a clear line from evidence to conclusion.'
            if context.objective_passed
            else f'"{context.quest_title}" didn\'t fully land, but the approach has real building blocks.'
        )

        payload = {
            "summary": summary,
            "strengths": strengths or ["Completed the quest."],
            "development_areas": development_areas,
            "capabilities": capabilities,
            "recommended_focus": recommended_focus,
        }
        return json.dumps(payload)


def get_ai_provider(provider_name: str) -> AIProvider:
    if provider_name == "mock":
        return MockAIProvider()
    # No other provider is configured in this project. Fail loudly and
    # explicitly rather than silently falling back — see AIProviderError.
    raise AIProviderError(
        f"Unknown or unconfigured AI provider: {provider_name!r}. "
        "Only 'mock' is available; set AI_PROVIDER=mock or implement a real provider."
    )

"""The strict contract an AI evaluation provider's output must satisfy
before any of it is trusted. Nothing here is persisted to a
CapabilityProfile until it has passed this validation — a malformed or
out-of-contract response is rejected outright (see
services/ai_evaluation_service.py), never partially applied.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.capability import CAPABILITY_KEYS
from app.models.capability_evidence import EVIDENCE_STRENGTHS


class AICapabilityAssessment(BaseModel):
    """One capability the AI says it observed evidence for, in one mission
    attempt. This is a claim about the *evidence*, not a numeric rating —
    `level` is qualitative and `confidence` reflects how sure the AI is
    that the evidence supports that level, not how "good" the employee is.
    """

    model_config = ConfigDict(extra="forbid")

    capability: str
    level: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = Field(min_length=1, max_length=500)

    @field_validator("capability")
    @classmethod
    def _known_capability(cls, v: str) -> str:
        if v not in CAPABILITY_KEYS:
            raise ValueError(f"Unsupported capability key: {v!r}. Must be one of {CAPABILITY_KEYS}")
        return v

    @field_validator("level")
    @classmethod
    def _valid_level(cls, v: str) -> str:
        # Deliberately NOT the full CAPABILITY_LEVELS list — NOT_OBSERVED
        # describes the *absence* of evidence, which the AI can't assert
        # about evidence it is, by definition, reporting on right now.
        if v not in EVIDENCE_STRENGTHS:
            raise ValueError(f"Invalid level: {v!r}. Must be one of {EVIDENCE_STRENGTHS}")
        return v


class AIEvaluationResponse(BaseModel):
    """The full structured contract. The AI interprets reasoning quality —
    it never determines mission completion, objective correctness, or any
    database truth; those stay deterministic (mission_scenarios.grade)."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=1000)
    strengths: list[str] = Field(max_length=10)
    development_areas: list[str] = Field(max_length=10)
    capabilities: list[AICapabilityAssessment] = Field(min_length=1, max_length=len(CAPABILITY_KEYS))
    recommended_focus: str = Field(min_length=1, max_length=500)

    @field_validator("capabilities")
    @classmethod
    def _no_duplicate_capabilities(cls, v: list[AICapabilityAssessment]) -> list[AICapabilityAssessment]:
        keys = [c.capability for c in v]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate capability keys in AI response")
        return v

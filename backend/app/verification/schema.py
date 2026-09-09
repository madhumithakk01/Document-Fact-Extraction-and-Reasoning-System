"""Typed structures for the verification loop."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.extraction.schema import AnchoredFact, CandidateFact


class VerificationStage(StrEnum):
    grounding_check = "grounding_check"
    independent_verify = "independent_verify"
    dual_extraction = "dual_extraction"


class IndependentVerdict(StrEnum):
    supported = "supported"
    partially_supported = "partially_supported"
    not_supported = "not_supported"


class VerificationOutcome(StrEnum):
    """Final state written to ``Fact.verification_status``."""

    verified = "verified"
    auto_corrected = "auto_corrected"
    needs_review = "needs_review"
    rejected = "rejected"


class GroundingResult(BaseModel):
    passed: bool
    reason: str
    normalized_evidence: str = ""
    matched_start: int | None = None
    matched_end: int | None = None


class VerifierIssue(BaseModel):
    field: str  # e.g. "value.number", "value.unit", "entity", "period", "other"
    problem: str
    suggested_correction: str | None = None


class IndependentVerification(BaseModel):
    verdict: IndependentVerdict
    issues: list[VerifierIssue] = Field(default_factory=list)
    supported_confidence: float = 0.0
    reasoning: str = ""
    provider: str = ""  # the LLM provider that served this verification call


class VerificationLogEntry(BaseModel):
    stage: VerificationStage
    result: str
    issue: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class FactVerification(BaseModel):
    fact: AnchoredFact
    final_status: VerificationOutcome
    verifier_confidence: float | None = None
    corrected: bool = False
    corrected_fact: CandidateFact | None = None
    log: list[VerificationLogEntry] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    # set when independent dual-extraction corroboration ran for this fact:
    # {status, confidence, corroborating_provider, needs_human_review, ...}
    corroboration: dict[str, Any] | None = None

    @property
    def effective_fact(self) -> CandidateFact:
        return self.corrected_fact or self.fact.candidate


class VerificationStats(BaseModel):
    facts_in: int = 0
    verified: int = 0
    auto_corrected: int = 0
    needs_review: int = 0
    rejected: int = 0
    grounding_failures: int = 0
    verifier_calls: int = 0
    verifier_errors: int = 0
    correction_attempts: int = 0

    def record(self, outcome: VerificationOutcome) -> None:
        setattr(self, outcome.value, getattr(self, outcome.value) + 1)


class VerificationResult(BaseModel):
    document_filename: str
    content_hash: str
    verifications: list[FactVerification]
    stats: VerificationStats

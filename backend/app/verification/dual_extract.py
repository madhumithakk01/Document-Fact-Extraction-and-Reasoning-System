"""Independent dual-extraction corroboration.

Instead of one model checking its own work, re-run the *same* extraction prompt
on a second, independent provider against the same raw source text, then reconcile
the two extractions through the existing deterministic precheck. A fact that a
blindly-sourced second extraction also produces (and that the precheck resolves
as corroborating) is genuinely two-source; one that no blind fact matches is
single-source and flagged for a human.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.comparison.precheck import ComparableFact, PrecheckOutcome, deterministic_precheck
from app.extraction.extractor import extract_from_chunk
from app.extraction.schema import AnchoredFact, CandidateFact
from app.ingestion.types import Chunk
from app.normalization.assumptions import detect_assumptions
from app.providers.base import LLMProvider

CORROBORATED = "independently_corroborated"
UNCONFIRMED = "single_source_unconfirmed"


@dataclass(frozen=True, slots=True)
class CorroborationResult:
    status: str
    confidence: float
    corroborating_provider: str | None = None
    needs_human_review: bool = False
    blind_provider: str | None = None
    blind_fact_count: int = 0

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "confidence": self.confidence,
            "corroborating_provider": self.corroborating_provider,
            "needs_human_review": self.needs_human_review,
            "blind_provider": self.blind_provider,
            "blind_fact_count": self.blind_fact_count,
        }


def _score(agree: bool, assumed_flags: list[str]) -> float:
    s = 0.65 + (0.25 if agree else -0.15) - 0.10 * len(assumed_flags)
    return max(0.05, min(0.99, s))


def comparable_of(candidate: CandidateFact) -> ComparableFact:
    """Adapt an extracted candidate to the precheck's input shape."""
    return ComparableFact(
        fact_kind=str(candidate.fact_kind.value),
        entity=candidate.entity,
        attribute=candidate.attribute,
        value=candidate.value.model_dump(exclude_none=True),
        period=candidate.period.model_dump(exclude_none=True),
        qualifiers=dict(candidate.qualifiers or {}),
        entity_resolved=candidate.entity_resolved,
    )


def assumed_flags_of(candidate: CandidateFact) -> list[str]:
    value = candidate.value.model_dump(exclude_none=True)
    return detect_assumptions(
        fact_kind=str(candidate.fact_kind.value),
        entity_resolved=candidate.entity_resolved,
        value=value,
        period_label=candidate.period.raw_label,
    )


async def blind_reextract(chunk: Chunk, provider: LLMProvider) -> list[AnchoredFact]:
    """Run the existing extraction prompt on ``provider`` against ``chunk``'s raw
    text, with zero knowledge of what the primary provider already extracted."""
    facts, _stats = await extract_from_chunk(chunk, provider)
    return facts


def independent_corroborate(
    primary: CandidateFact,
    blind_facts: list[CandidateFact],
    *,
    blind_provider: str | None = None,
) -> CorroborationResult:
    """Reconcile a primary fact against a blindly-sourced second extraction using
    only the deterministic precheck -- no new comparison logic, no third model."""
    primary_cf = comparable_of(primary)
    flags = assumed_flags_of(primary)

    for candidate in blind_facts:
        result = deterministic_precheck(primary_cf, comparable_of(candidate))
        # the precheck only ever *positively* resolves "corroborates"; a context
        # reconciliation is a downstream agent outcome, never a precheck one
        if result.outcome is PrecheckOutcome.corroborates:
            return CorroborationResult(
                status=CORROBORATED,
                confidence=_score(True, flags),
                corroborating_provider=blind_provider,
                blind_provider=blind_provider,
                blind_fact_count=len(blind_facts),
            )

    return CorroborationResult(
        status=UNCONFIRMED,
        confidence=_score(False, flags),
        needs_human_review=True,
        blind_provider=blind_provider,
        blind_fact_count=len(blind_facts),
    )

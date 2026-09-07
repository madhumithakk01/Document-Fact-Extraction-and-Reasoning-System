from __future__ import annotations

from app.extraction.schema import ExtractionResult, ExtractionStats
from app.verification.pipeline import verify_extraction
from tests.verification.conftest import ScriptedProvider, issue, verdict

_EV = "FY24 consolidated EBITDA was INR 127 Crore"
_CHUNK = f"Preamble. {_EV}. Trailer."


def _extraction(anchored_facts) -> ExtractionResult:
    return ExtractionResult(
        document_filename="doc.pdf",
        content_hash="abc123",
        facts=anchored_facts,
        stats=ExtractionStats(facts_kept=len(anchored_facts)),
    )


async def test_pipeline_aggregates_mixed_outcomes(make_anchored, make_chunk) -> None:
    good = make_anchored(evidence_text=_EV, chunk_index=0)
    ungrounded = make_anchored(evidence_text="this quote is nowhere on the page", chunk_index=0)
    fixable = make_anchored(
        evidence_text=_EV,
        chunk_index=0,
        value={"comparator": "eq", "number": 127.0, "unit": "INR Lakh"},
    )

    provider = ScriptedProvider(
        verify_responses=[
            verdict("supported", confidence=0.9),  # good
            verdict(  # fixable, first pass
                "partially_supported",
                confidence=0.3,
                issues=[issue("value.unit", "should be Crore", "INR Crore")],
            ),
            verdict("supported", confidence=0.8),  # fixable, recheck
        ]
    )
    chunks = [make_chunk(_CHUNK, index=0)]

    result = await verify_extraction(
        _extraction([good, ungrounded, fixable]), chunks, provider=provider, concurrency=1
    )
    s = result.stats
    assert s.facts_in == 3
    assert s.verified == 1
    assert s.auto_corrected == 1
    assert s.rejected == 1
    assert s.grounding_failures == 1
    assert s.correction_attempts == 1
    assert s.verified + s.auto_corrected + s.needs_review + s.rejected == s.facts_in


async def test_unanchored_fact_is_rejected_by_grounding(make_anchored, make_chunk) -> None:
    from app.extraction.schema import AnchoredFact

    bare = AnchoredFact(candidate=make_anchored(evidence_text=_EV).candidate, anchor=None)
    provider = ScriptedProvider(verify_responses=[])
    result = await verify_extraction(_extraction([bare]), [make_chunk(_CHUNK)], provider=provider)
    assert result.stats.rejected == 1
    assert provider.verify_calls == []

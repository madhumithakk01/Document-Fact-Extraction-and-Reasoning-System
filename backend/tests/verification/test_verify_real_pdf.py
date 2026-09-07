"""Live end-to-end verification against a real source PDF.

Runs only when a provider is reachable (GROQ_API_KEY set, or Ollama local).
Also checks that a deliberately corrupted fact does not pass verification.
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

import pytest

from app.extraction import extract_document
from app.extraction.schema import AnchoredFact, ExtractionResult
from app.ingestion import ingest_pdf
from app.providers.factory import get_llm_provider
from app.verification import verify_extraction
from app.verification.schema import VerificationOutcome
from app.verification.verifier import verify_fact

_DATASETS = Path(__file__).resolve().parents[3] / "datasets"
_DECK = _DATASETS / "delhivery" / "03-delhivery-q4-fy24-earnings-presentation.pdf"


def _provider_available() -> bool:
    if os.getenv("GROQ_API_KEY"):
        return True
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1)
        return True
    except Exception:
        return False


pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not _DECK.is_file(), reason="datasets/ not available"),
    pytest.mark.skipif(not _provider_available(), reason="no LLM provider reachable"),
]


async def test_verification_produces_valid_outcomes_and_catches_a_bad_fact() -> None:
    ingestion = ingest_pdf(_DECK.read_bytes(), _DECK.name, render_images=False)
    provider = get_llm_provider()
    try:
        extraction: ExtractionResult = await extract_document(
            ingestion, provider=provider, pages=[5], concurrency=1
        )
        assert extraction.facts, "expected facts from the FY24 highlights slide"

        result = await verify_extraction(
            extraction, ingestion.chunks, provider=provider, concurrency=1
        )
        assert result.stats.facts_in == len(extraction.facts)
        for fv in result.verifications:
            assert fv.final_status in set(VerificationOutcome)
            if fv.final_status is VerificationOutcome.rejected:
                assert any(
                    e.stage.value == "grounding_check" and e.result == "fail" for e in fv.log
                )
            if fv.final_status is VerificationOutcome.verified:
                assert fv.verifier_confidence is not None

        # take a genuinely verified fact and corrupt its number by 10x
        verified = next(
            (fv for fv in result.verifications if fv.final_status is VerificationOutcome.verified),
            None,
        )
        if verified is None:
            pytest.skip("no cleanly verified fact to corrupt in this run")

        good = verified.fact
        bad_candidate = good.candidate.model_copy(deep=True)
        if bad_candidate.value.number is None:
            pytest.skip("verified fact is not quantitative")
        bad_candidate.value.number *= 10
        bad = AnchoredFact(candidate=bad_candidate, anchor=good.anchor)

        chunk = next(c for c in ingestion.chunks if c.index == good.anchor.chunk_index)
        bad_fv = await verify_fact(bad, chunk, provider)
        assert bad_fv.final_status is not VerificationOutcome.verified
    finally:
        await provider.aclose()

"""Live extraction against a real source PDF.

Runs only when a provider is actually reachable: GROQ_API_KEY set, or Ollama
answering locally. Otherwise skipped, like the ingestion real-PDF suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.extraction import extract_document
from app.extraction.schema import FactKind
from app.ingestion import ingest_pdf
from app.providers.factory import get_llm_provider
from tests._env import provider_available

_DATASETS = Path(__file__).resolve().parents[3] / "datasets"
_DECK = _DATASETS / "delhivery" / "03-delhivery-q4-fy24-earnings-presentation.pdf"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not _DECK.is_file(), reason="datasets/ not available"),
    pytest.mark.skipif(not provider_available(), reason="no LLM provider reachable"),
]


async def test_extracts_plausible_anchored_facts_from_the_earnings_deck() -> None:
    ingestion = ingest_pdf(_DECK.read_bytes(), _DECK.name, render_images=False)
    provider = get_llm_provider()
    try:
        result = await extract_document(
            ingestion, provider=provider, pages=[4, 5, 6, 7], concurrency=2
        )
    finally:
        await provider.aclose()

    assert result.stats.llm_calls >= 1
    assert result.facts, "expected at least one fact from the FY24 highlights pages"

    anchored = [f for f in result.facts if f.anchored]
    assert len(anchored) >= len(result.facts) * 0.6

    for f in anchored:
        # the anchor points into the real document text
        assert f.anchor.char_start < f.anchor.char_end
        assert f.candidate.fact_kind in set(FactKind)
        if f.candidate.fact_kind is FactKind.quantitative:
            assert f.candidate.value.comparator is not None

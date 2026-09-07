"""End-to-end: real PDF -> extract -> verify -> deterministic pre-check.

Slow and provider-gated. Confirms the pre-check runs over real verified facts
without raising and without making a model call of its own.
"""

from __future__ import annotations

import itertools
import os
import urllib.request
from pathlib import Path

import pytest

from app.comparison.precheck import ComparableFact, PrecheckOutcome, deterministic_precheck
from app.extraction import extract_document
from app.ingestion import ingest_pdf
from app.providers.factory import get_llm_provider
from app.verification import verify_extraction
from app.verification.schema import VerificationOutcome

_DECK = (
    Path(__file__).resolve().parents[3]
    / "datasets"
    / "delhivery"
    / "03-delhivery-q4-fy24-earnings-presentation.pdf"
)


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


async def test_precheck_runs_over_real_verified_facts() -> None:
    ingestion = ingest_pdf(_DECK.read_bytes(), _DECK.name, render_images=False)
    provider = get_llm_provider()
    try:
        extraction = await extract_document(ingestion, provider=provider, pages=[5], concurrency=1)
        verification = await verify_extraction(
            extraction, ingestion.chunks, provider=provider, concurrency=1
        )
    finally:
        await provider.aclose()

    facts = [
        ComparableFact(
            fact_kind=fv.effective_fact.fact_kind.value,
            entity=fv.effective_fact.entity,
            attribute=fv.effective_fact.attribute,
            value=fv.effective_fact.value.model_dump(exclude_none=True),
            period=fv.effective_fact.period.model_dump(exclude_none=True),
            qualifiers=fv.effective_fact.qualifiers,
        )
        for fv in verification.verifications
        if fv.final_status in (VerificationOutcome.verified, VerificationOutcome.auto_corrected)
    ]
    assert facts, "expected some usable facts from the FY24 highlights slide"

    for a, b in itertools.combinations(facts, 2):
        result = deterministic_precheck(a, b)
        assert result.outcome in set(PrecheckOutcome)
        assert isinstance(result.reason, str) and result.reason

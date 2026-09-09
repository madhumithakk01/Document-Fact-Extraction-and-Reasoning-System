"""verify_extraction wires independent dual-extraction corroboration in: one
blind re-extraction per chunk on the alternate provider, precheck reconciliation,
and the score replacing the flat verifier confidence."""

from __future__ import annotations

import pytest

from app.extraction.schema import ExtractionResult, ExtractionStats
from app.verification.pipeline import verify_extraction
from app.verification.schema import VerificationOutcome
from tests.extraction.conftest import fact_payload, make_provider
from tests.verification.conftest import ScriptedProvider, verdict

_CHUNK_TEXT = (
    "Acme Corporation reported results for the year. Consolidated revenue was "
    "INR 8,142 Crore. The company also disclosed an employee headcount of 45,000 "
    "people across all regions as at the period end. Both figures are audited."
)


@pytest.fixture
def _enable_dual_extract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUAL_EXTRACT_MODE", "all")
    monkeypatch.setenv("DUAL_EXTRACT_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    from app.config import get_settings

    get_settings.cache_clear()


def _extraction(make_anchored) -> tuple[ExtractionResult, list]:
    revenue = make_anchored(
        evidence_text="Consolidated revenue was INR 8,142 Crore",
        entity="Acme Corporation",
        attribute="consolidated revenue",
        value={"comparator": "eq", "number": 8142.0, "unit": "INR Crore"},
        period="calendar year 2024",
        chunk_index=0,
    )
    headcount = make_anchored(
        evidence_text="employee headcount of 45,000 people",
        entity="Acme Corporation",
        attribute="employee headcount",
        value={"comparator": "eq", "number": 45000.0, "unit": "people"},
        period="calendar year 2024",
        chunk_index=0,
    )
    result = ExtractionResult(
        document_filename="acme.pdf",
        content_hash="hash",
        facts=[revenue, headcount],
        stats=ExtractionStats(),
    )
    return result, [revenue, headcount]


async def test_blind_agreement_corroborates_and_replaces_confidence(
    _enable_dual_extract, make_anchored, make_chunk, monkeypatch
) -> None:
    extraction, _ = _extraction(make_anchored)
    chunk = make_chunk(_CHUNK_TEXT, index=0)

    # the blind provider re-extracts only the revenue figure
    blind = make_provider(
        {
            "facts": [
                fact_payload(
                    attribute="consolidated revenue",
                    evidence_text="Consolidated revenue was INR 8,142 Crore",
                    value={"comparator": "eq", "number": 8142.0, "unit": "Rs Cr"},
                    period={"raw_label": "calendar year 2024"},
                )
            ]
        }
    )
    monkeypatch.setattr(
        "app.verification.pipeline.build_single_provider", lambda *a, **k: blind
    )

    verifier = ScriptedProvider(verify_responses=[verdict("supported", confidence=0.71)] * 2)
    result = await verify_extraction(extraction, [chunk], provider=verifier)

    by_attr = {v.effective_fact.attribute: v for v in result.verifications}

    rev = by_attr["consolidated revenue"]
    assert rev.corroboration["status"] == "independently_corroborated"
    assert rev.corroboration["corroborating_provider"] == "fake"
    assert rev.verifier_confidence == pytest.approx(0.90)  # _score(agree=True, no flags)
    assert rev.final_status is VerificationOutcome.verified

    head = by_attr["employee headcount"]
    assert head.corroboration["status"] == "single_source_unconfirmed"
    assert head.corroboration["needs_human_review"] is True
    assert head.verifier_confidence == pytest.approx(0.50)
    assert head.final_status is VerificationOutcome.needs_review

    # one blind re-extraction for the shared chunk, not one per fact
    assert len(blind.calls) == 1


async def test_off_mode_does_no_corroboration(
    make_anchored, make_chunk, monkeypatch
) -> None:
    monkeypatch.setenv("DUAL_EXTRACT_MODE", "off")
    from app.config import get_settings

    get_settings.cache_clear()

    extraction, _ = _extraction(make_anchored)
    verifier = ScriptedProvider(verify_responses=[verdict("supported")] * 2)
    chunks = [make_chunk(_CHUNK_TEXT, index=0)]
    result = await verify_extraction(extraction, chunks, provider=verifier)

    assert all(v.corroboration is None for v in result.verifications)

from __future__ import annotations

from app.verification.schema import VerificationOutcome
from app.verification.verifier import verify_fact
from tests.verification.conftest import ScriptedProvider, issue, verdict

_EVIDENCE = "FY24 consolidated EBITDA was INR 127 Crore"
_CHUNK_TEXT = f"Some preamble on this page. {_EVIDENCE}. And a closing sentence."


async def test_grounding_failure_rejects_without_calling_verifier(
    make_anchored, make_chunk
) -> None:
    af = make_anchored(evidence_text="a sentence that is not on the page at all here")
    provider = ScriptedProvider(verify_responses=[verdict("supported")])
    fv = await verify_fact(af, make_chunk(_CHUNK_TEXT), provider)
    assert fv.final_status is VerificationOutcome.rejected
    assert provider.verify_calls == []
    assert fv.log[0].stage.value == "grounding_check" and fv.log[0].result == "fail"


async def test_supported_becomes_verified(make_anchored, make_chunk) -> None:
    af = make_anchored(evidence_text=_EVIDENCE)
    provider = ScriptedProvider(verify_responses=[verdict("supported", confidence=0.92)])
    fv = await verify_fact(af, make_chunk(_CHUNK_TEXT), provider)
    assert fv.final_status is VerificationOutcome.verified
    assert fv.verifier_confidence == 0.92
    assert [e.stage.value for e in fv.log] == ["grounding_check", "independent_verify"]


async def test_low_confidence_support_is_not_accepted(make_anchored, make_chunk) -> None:
    af = make_anchored(evidence_text=_EVIDENCE)
    provider = ScriptedProvider(verify_responses=[verdict("supported", confidence=0.2)])
    fv = await verify_fact(af, make_chunk(_CHUNK_TEXT), provider)
    assert fv.final_status is VerificationOutcome.needs_review


async def test_not_supported_without_correction_needs_review(make_anchored, make_chunk) -> None:
    af = make_anchored(evidence_text=_EVIDENCE)
    provider = ScriptedProvider(
        verify_responses=[verdict("not_supported", issues=[issue("entity", "ambiguous")])]
    )
    fv = await verify_fact(af, make_chunk(_CHUNK_TEXT), provider)
    assert fv.final_status is VerificationOutcome.needs_review
    assert not fv.corrected


async def test_auto_correct_then_supported(make_anchored, make_chunk) -> None:
    af = make_anchored(
        evidence_text=_EVIDENCE,
        value={"comparator": "eq", "number": 127.0, "unit": "INR Lakh"},
    )
    provider = ScriptedProvider(
        verify_responses=[
            verdict(
                "partially_supported",
                confidence=0.3,
                issues=[issue("value.unit", "unit is Crore not Lakh", "INR Crore")],
            ),
            verdict("supported", confidence=0.88),
        ]
    )
    fv = await verify_fact(af, make_chunk(_CHUNK_TEXT), provider)
    assert fv.final_status is VerificationOutcome.auto_corrected
    assert fv.corrected and fv.corrected_fact.value.unit == "INR Crore"
    assert fv.verifier_confidence == 0.88
    assert len(provider.verify_calls) == 2
    assert any("auto-corrected" in n for n in fv.notes)


async def test_auto_correct_then_still_not_supported_needs_review(
    make_anchored, make_chunk
) -> None:
    af = make_anchored(evidence_text=_EVIDENCE)
    provider = ScriptedProvider(
        verify_responses=[
            verdict("not_supported", issues=[issue("value.number", "should be 128", "128")]),
            verdict("not_supported", confidence=0.1),
        ]
    )
    fv = await verify_fact(af, make_chunk(_CHUNK_TEXT), provider)
    assert fv.final_status is VerificationOutcome.needs_review
    assert len(provider.verify_calls) == 2


async def test_verifier_error_flags_needs_review(make_anchored, make_chunk) -> None:
    from app.providers.base import ProviderError

    af = make_anchored(evidence_text=_EVIDENCE)
    provider = ScriptedProvider(verify_responses=[ProviderError("503 upstream")])
    fv = await verify_fact(af, make_chunk(_CHUNK_TEXT), provider)
    assert fv.final_status is VerificationOutcome.needs_review
    assert any(e.result == "error" for e in fv.log)


async def test_missing_chunk_fails_grounding(make_anchored) -> None:
    af = make_anchored(evidence_text=_EVIDENCE)
    provider = ScriptedProvider(verify_responses=[verdict("supported")])
    fv = await verify_fact(af, None, provider)
    assert fv.final_status is VerificationOutcome.rejected

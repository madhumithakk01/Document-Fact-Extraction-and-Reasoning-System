from __future__ import annotations

import json

from app.comparison.adjudicator import (
    Adjudication,
    RelationshipType,
    adjudicate_pair,
    build_prompt,
)
from app.comparison.precheck import ComparableFact
from app.providers.base import CompletionRequest, CompletionResult, LLMProvider


class _Provider(LLMProvider):
    name = "fake"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.last: CompletionRequest | None = None

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.last = request
        return CompletionResult(text=json.dumps(self.payload), model="m", provider="fake")

    async def health_check(self) -> bool:
        return True


def _verdict(rt: str, **over) -> dict:
    base = {
        "entity_match": True,
        "attribute_match": True,
        "period_relation": "same",
        "unit_scale_note": "127 Cr = 1266.41 million",
        "qualifier_explanation": "none differ",
        "comparator_consistent": True,
        "relationship_type": rt,
        "reconciliation_basis": None,
        "explanation": "the figures agree once scaled",
        "confidence": 0.9,
        "needs_more_context": False,
        "missing_context": None,
    }
    base.update(over)
    return base


A = ComparableFact(
    "quantitative",
    "Delhivery",
    "FY24 EBITDA",
    {"comparator": "eq", "number": 127, "unit": "INR Crore"},
    {"raw_label": "FY24"},
)
B = ComparableFact(
    "quantitative",
    "Delhivery",
    "FY24 EBITDA",
    {"comparator": "eq", "number": 1266.41, "unit": "INR million"},
    {"raw_label": "FY2023-24"},
)


def test_build_prompt_includes_both_facts_and_evidence() -> None:
    prompt = build_prompt(A, "EBITDA was INR 127 Cr", B, "EBITDA of INR 1,266.41 million")
    assert "FACT A" in prompt and "FACT B" in prompt
    assert "INR 127 Cr" in prompt and "1,266.41 million" in prompt


async def test_corroborates_verdict() -> None:
    p = _Provider(_verdict("corroborates"))
    adj = await adjudicate_pair(A, "e1", B, "e2", p)
    assert adj.relationship_type is RelationshipType.corroborates
    assert adj.reconciliation_basis is None


async def test_contradicts_verdict() -> None:
    p = _Provider(
        _verdict("contradicts", explanation="6.5% vs 6.6%, nothing explains it", confidence=0.8)
    )
    adj = await adjudicate_pair(A, "e1", B, "e2", p)
    assert adj.relationship_type is RelationshipType.contradicts


async def test_reconciled_keeps_named_basis() -> None:
    p = _Provider(
        _verdict("reconciled_by_context", reconciliation_basis="different consolidation basis")
    )
    adj = await adjudicate_pair(A, "e1", B, "e2", p)
    assert adj.relationship_type is RelationshipType.reconciled_by_context
    assert adj.reconciliation_basis == "different consolidation basis"


def test_from_payload_drops_basis_unless_reconciled() -> None:
    adj = Adjudication.from_payload(
        _verdict("corroborates", reconciliation_basis="should be ignored")
    )
    assert adj.reconciliation_basis is None


def test_from_payload_clamps_confidence() -> None:
    assert Adjudication.from_payload(_verdict("corroborates", confidence=3.0)).confidence == 1.0


async def test_final_pass_suppresses_needs_more_context() -> None:
    p = _Provider(_verdict("contradicts", needs_more_context=True, missing_context="x"))
    adj = await adjudicate_pair(A, "e1", B, "e2", p, allow_more_context=False)
    assert adj.needs_more_context is False
    assert "final decision" in (p.last.user if p.last else "")

from __future__ import annotations

import json

from app.comparison.canonicalize import adjudicate_same_concept
from app.providers.base import CompletionRequest, CompletionResult, LLMProvider, ProviderError


class _Provider(LLMProvider):
    name = "fake"

    def __init__(self, payload: object) -> None:
        self._payload = payload
        self.calls = 0

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.calls += 1
        if isinstance(self._payload, Exception):
            raise self._payload
        return CompletionResult(text=json.dumps(self._payload), model="m", provider="fake")

    async def health_check(self) -> bool:
        return True


async def test_exact_match_skips_the_model() -> None:
    p = _Provider({})
    d = await adjudicate_same_concept("EBITDA", "ebitda", "attribute", p)
    assert d.same_concept and d.method == "exact"
    assert p.calls == 0


async def test_reordered_tokens_skip_the_model() -> None:
    p = _Provider({})
    d = await adjudicate_same_concept("growth of GDP", "GDP growth", "attribute", p)
    assert d.same_concept and d.method == "exact"
    assert p.calls == 0


async def test_clearly_unrelated_labels_skip_the_model() -> None:
    p = _Provider({})
    d = await adjudicate_same_concept("EBITDA", "number of employees", "attribute", p)
    assert not d.same_concept and d.method == "disjoint"
    assert p.calls == 0


async def test_uncertain_pair_asks_the_model() -> None:
    p = _Provider(
        {"same_concept": True, "canonical_name": "consolidated EBITDA", "reasoning": "same"}
    )
    d = await adjudicate_same_concept(
        "consolidated EBITDA", "EBITDA (consolidated basis)", "attribute", p
    )
    assert p.calls == 1
    assert d.same_concept and d.canonical_name == "consolidated EBITDA"
    assert d.method == "model"


async def test_model_says_not_the_same() -> None:
    p = _Provider({"same_concept": False, "canonical_name": "x", "reasoning": "different scope"})
    d = await adjudicate_same_concept("gross revenue", "net revenue", "attribute", p)
    assert p.calls == 1
    assert not d.same_concept


async def test_model_error_defaults_to_not_merging() -> None:
    p = _Provider(ProviderError("503"))
    d = await adjudicate_same_concept(
        "segment revenue", "revenue by segment reported", "attribute", p
    )
    assert not d.same_concept
    assert d.method == "model_error"

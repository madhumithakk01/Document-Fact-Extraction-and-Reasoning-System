"""Scripted provider that answers extraction and verification calls separately."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from app.extraction.schema import AnchoredFact, CandidateFact, SourceAnchor
from app.ingestion.types import Chunk
from app.providers.base import CompletionRequest, CompletionResult, LLMProvider, ProviderError
from app.verification.prompts import INDEPENDENT_VERIFY_SYSTEM


class ScriptedProvider(LLMProvider):
    """``verify_responses`` are consumed in order for successive verifier calls
    (first check, then any recheck). Each entry is a dict payload, a raw str, or
    an Exception instance to raise."""

    name = "scripted"

    def __init__(self, verify_responses: list[object] | None = None) -> None:
        self._verify = list(verify_responses or [])
        self.verify_calls: list[CompletionRequest] = []

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        if request.system.startswith(INDEPENDENT_VERIFY_SYSTEM[:40]):
            self.verify_calls.append(request)
            if not self._verify:
                raise ProviderError("no scripted verify response left")
            item = self._verify.pop(0)
            if isinstance(item, Exception):
                raise item
            text = item if isinstance(item, str) else json.dumps(item)
            return CompletionResult(text=text, model="scripted", provider=self.name)
        raise ProviderError("this scripted provider only answers verification calls")

    async def health_check(self) -> bool:
        return True


def verdict(
    v: str,
    *,
    confidence: float = 0.9,
    issues: list[dict] | None = None,
    reasoning: str = "",
) -> dict:
    return {
        "verdict": v,
        "issues": issues or [],
        "supported_confidence": confidence,
        "reasoning": reasoning,
    }


def issue(field: str, problem: str, correction: str | None = None) -> dict:
    return {"field": field, "problem": problem, "suggested_correction": correction}


@pytest.fixture
def make_anchored() -> Callable[..., AnchoredFact]:
    def _factory(
        *,
        evidence_text: str,
        entity: str = "Delhivery",
        attribute: str = "FY24 consolidated EBITDA",
        fact_kind: str = "quantitative",
        value: dict | None = None,
        period: str | None = "FY24",
        chunk_index: int = 0,
        page_number: int = 5,
        matched_text: str | None = None,
    ) -> AnchoredFact:
        candidate = CandidateFact.model_validate(
            {
                "fact_kind": fact_kind,
                "entity": entity,
                "attribute": attribute,
                "evidence_text": evidence_text,
                "value": value or {"comparator": "eq", "number": 127.0, "unit": "INR Crore"},
                "period": {"raw_label": period},
            }
        )
        anchor = SourceAnchor(
            chunk_index=chunk_index,
            page_number=page_number,
            char_start=1000,
            char_end=1000 + len(evidence_text),
            matched_text=matched_text or evidence_text,
            exact=True,
        )
        return AnchoredFact(candidate=candidate, anchor=anchor)

    return _factory


@pytest.fixture
def make_chunk() -> Callable[..., Chunk]:
    def _factory(text: str, *, index: int = 0, page_number: int = 5) -> Chunk:
        return Chunk(
            page_number=page_number,
            index=index,
            text=text,
            char_start=1000,
            char_end=1000 + len(text),
        )

    return _factory

"""A scripted LLM provider so extraction tests never touch the network."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from app.ingestion.types import Chunk, PageContentType
from app.providers.base import CompletionRequest, CompletionResult, LLMProvider, ProviderError

Responder = Callable[[CompletionRequest], object]


class FakeLLMProvider(LLMProvider):
    """Returns whatever ``responder`` produces, serialized as the completion text.

    ``responder`` may return a dict/list (serialized to JSON), a str (sent as-is),
    or raise ``ProviderError`` to simulate a transport/parse failure.
    """

    name = "fake"

    def __init__(self, responder: Responder) -> None:
        self._responder = responder
        self.calls: list[CompletionRequest] = []

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.calls.append(request)
        payload = self._responder(request)
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return CompletionResult(text=text, model="fake-1", provider=self.name)

    async def health_check(self) -> bool:
        return True


def make_provider(payload_or_fn: object | Responder) -> FakeLLMProvider:
    if callable(payload_or_fn):
        return FakeLLMProvider(payload_or_fn)
    return FakeLLMProvider(lambda _req: payload_or_fn)


def failing_provider() -> FakeLLMProvider:
    def _boom(_req: CompletionRequest) -> object:
        raise ProviderError("simulated upstream 503")

    return FakeLLMProvider(_boom)


@pytest.fixture
def make_chunk() -> Callable[..., Chunk]:
    def _factory(
        text: str,
        *,
        index: int = 0,
        page_number: int = 1,
        char_start: int = 1000,
        leading_context: str = "",
        table_markdown: str | None = None,
        confidence_ceiling: float = 1.0,
        content_type: PageContentType = PageContentType.text_native,
    ) -> Chunk:
        return Chunk(
            page_number=page_number,
            index=index,
            text=text,
            leading_context=leading_context,
            char_start=char_start,
            char_end=char_start + len(text),
            has_table=table_markdown is not None,
            table_markdown=table_markdown,
            content_type=content_type,
            confidence_ceiling=confidence_ceiling,
        )

    return _factory


def fact_payload(**overrides: object) -> dict:
    """A single well-formed candidate fact, override any field."""
    base = {
        "fact_kind": "quantitative",
        "entity": "Acme Corporation",
        "entity_resolved": True,
        "attribute": "consolidated revenue",
        "value": {
            "comparator": "eq",
            "number": 8142.0,
            "number_high": None,
            "unit": "INR Crore",
            "state": None,
            "text": None,
        },
        "period": {"raw_label": "FY24", "start_date": None, "end_date": None},
        "qualifiers": {"basis": "consolidated"},
        "evidence_text": "consolidated revenue was INR 8,142 Crore in FY24",
        "extraction_confidence": 0.9,
    }
    base.update(overrides)
    return base

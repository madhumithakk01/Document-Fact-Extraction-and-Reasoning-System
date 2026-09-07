from __future__ import annotations

import pytest

from app.providers.base import CompletionRequest, CompletionResult, ProviderError
from app.providers.openai_compatible import OpenAICompatibleProvider


def test_completion_result_parses_json() -> None:
    result = CompletionResult(text='{"a": 1}', model="m", provider="p")
    assert result.json() == {"a": 1}


def test_completion_result_json_raises_on_prose() -> None:
    result = CompletionResult(text="not json at all", model="m", provider="p")
    with pytest.raises(ProviderError, match="expected JSON"):
        result.json()


def test_schema_request_sets_strict_response_format() -> None:
    provider = OpenAICompatibleProvider(
        name="groq",
        base_url="https://example.invalid",
        api_key="k",
        model="llama-3.3-70b-versatile",
        default_temperature=0.0,
        default_max_tokens=256,
        timeout_seconds=1.0,
    )
    schema = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    payload = provider._payload(
        CompletionRequest(system="s", user="u", json_schema=schema, max_tokens=10)
    )
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["response_format"]["json_schema"]["schema"] == schema
    assert payload["max_tokens"] == 10
    assert payload["temperature"] == 0.0

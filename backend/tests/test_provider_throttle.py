"""The OpenAI-compatible provider paces itself to stay within a token budget."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from app.providers.base import CompletionRequest, ProviderError
from app.providers.observability import RetryNotice, reset_retry_observer, set_retry_observer
from app.providers.openai_compatible import OpenAICompatibleProvider


def _provider_with_handler(handler, **kw) -> OpenAICompatibleProvider:  # noqa: ANN001, ANN003
    p = OpenAICompatibleProvider(
        name="test",
        base_url="https://example.invalid",
        api_key="k",
        model="m",
        default_temperature=0.0,
        default_max_tokens=64,
        timeout_seconds=5.0,
        min_request_interval=0.0,
        **kw,
    )
    p._client = httpx.AsyncClient(
        base_url="https://example.invalid", transport=httpx.MockTransport(handler)
    )
    return p


def _ok_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "m",
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            "usage": {},
        },
    )


def _provider(**kw) -> OpenAICompatibleProvider:  # noqa: ANN003
    p = OpenAICompatibleProvider(
        name="test",
        base_url="https://example.invalid",
        api_key="k",
        model="m",
        default_temperature=0.0,
        default_max_tokens=64,
        timeout_seconds=5.0,
        **kw,
    )

    async def _handler(_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return httpx.Response(
            200,
            json={
                "model": "m",
                "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                "usage": {},
            },
        )

    p._client = httpx.AsyncClient(
        base_url="https://example.invalid", transport=httpx.MockTransport(_handler)
    )
    return p


async def test_concurrency_cap_serializes_requests() -> None:
    # each mocked request takes ~0.05s; three of them under a cap of 1 run back
    # to back (~0.15s), whereas a cap of 3 would overlap (~0.05s).
    req = CompletionRequest(system="s", user="u")
    capped = _provider(max_concurrency=1)
    t0 = time.perf_counter()
    await asyncio.gather(*(capped.complete(req) for _ in range(3)))
    serial = time.perf_counter() - t0
    await capped.aclose()

    parallel_provider = _provider(max_concurrency=3)
    t0 = time.perf_counter()
    await asyncio.gather(*(parallel_provider.complete(req) for _ in range(3)))
    parallel = time.perf_counter() - t0
    await parallel_provider.aclose()

    assert serial > parallel * 1.8


async def test_min_interval_spaces_out_requests() -> None:
    provider = _provider(max_concurrency=1, min_request_interval=0.2)
    t0 = time.perf_counter()
    for _ in range(3):
        await provider.complete(CompletionRequest(system="s", user="u"))
    elapsed = time.perf_counter() - t0
    # 3 calls, 2 gaps of >= 0.2s each
    assert elapsed >= 0.4
    await provider.aclose()


@pytest.mark.parametrize("interval", [0.0])
async def test_no_interval_does_not_stall(interval: float) -> None:
    provider = _provider(min_request_interval=interval)
    t0 = time.perf_counter()
    await provider.complete(CompletionRequest(system="s", user="u"))
    assert time.perf_counter() - t0 < 1.0
    await provider.aclose()


async def test_rate_limit_retry_notifies_the_observer_then_succeeds() -> None:
    calls = {"n": 0}

    async def _handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, json={"error": "slow down"})
        return _ok_response()

    provider = _provider_with_handler(_handler)
    seen: list[RetryNotice] = []

    async def _observer(notice: RetryNotice) -> None:
        seen.append(notice)

    token = set_retry_observer(_observer)
    try:
        result = await provider.complete(CompletionRequest(system="s", user="u"))
    finally:
        reset_retry_observer(token)
        await provider.aclose()

    assert result.text == "{}"
    assert [n.status_code for n in seen] == [429]
    assert seen[0].attempt == 1
    assert seen[0].max_attempts == 5


async def test_retry_ceiling_raises_provider_error_after_max_attempts() -> None:
    calls = {"n": 0}

    async def _handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, headers={"retry-after": "0"}, json={"error": "nope"})

    provider = _provider_with_handler(_handler, max_retries=3)
    try:
        with pytest.raises(ProviderError):
            await provider.complete(CompletionRequest(system="s", user="u"))
    finally:
        await provider.aclose()

    assert calls["n"] == 4  # one initial attempt + three retries

"""The OpenAI-compatible provider paces itself to stay within a token budget."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from app.providers.base import CompletionRequest
from app.providers.openai_compatible import OpenAICompatibleProvider


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

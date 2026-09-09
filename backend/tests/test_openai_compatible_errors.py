"""The OpenAI-compatible provider raises typed errors so a fallback path can
tell 'try another provider' failures apart from real bugs."""

from __future__ import annotations

import httpx
import pytest

from app.providers.base import (
    CompletionRequest,
    ProviderAuthError,
    ProviderError,
    ProviderTimeoutError,
    RateLimitError,
)
from app.providers.openai_compatible import OpenAICompatibleProvider

_REQ = CompletionRequest(system="s", user="u")


def _provider(handler) -> OpenAICompatibleProvider:  # noqa: ANN001
    p = OpenAICompatibleProvider(
        name="groq",
        base_url="https://example.invalid",
        api_key="k",
        model="m",
        default_temperature=0.0,
        default_max_tokens=64,
        timeout_seconds=5.0,
        max_retries=0,
        min_request_interval=0.0,
    )
    p._client = httpx.AsyncClient(
        base_url="https://example.invalid", transport=httpx.MockTransport(handler)
    )
    return p


async def test_429_after_retries_is_a_rate_limit_error() -> None:
    provider = _provider(lambda _req: httpx.Response(429, text="rate limit reached"))
    with pytest.raises(RateLimitError, match="rate limited"):
        await provider.complete(_REQ)
    await provider.aclose()


@pytest.mark.parametrize("code", [401, 403])
async def test_auth_rejection_is_a_provider_auth_error(code: int) -> None:
    provider = _provider(lambda _req: httpx.Response(code, text="invalid api key"))
    with pytest.raises(ProviderAuthError):
        await provider.complete(_REQ)
    await provider.aclose()


async def test_timeout_is_a_provider_timeout_error() -> None:
    def _timeout(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    provider = _provider(_timeout)
    with pytest.raises(ProviderTimeoutError):
        await provider.complete(_REQ)
    await provider.aclose()


async def test_other_4xx_stays_a_generic_provider_error() -> None:
    provider = _provider(lambda _req: httpx.Response(400, text="bad request"))
    with pytest.raises(ProviderError) as excinfo:
        await provider.complete(_REQ)
    assert not isinstance(excinfo.value, (RateLimitError, ProviderAuthError, ProviderTimeoutError))
    await provider.aclose()

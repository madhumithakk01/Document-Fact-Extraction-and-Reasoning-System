"""FallbackLLMProvider: fail over to the secondary only on 'cannot serve now'
errors, and tag the result with whichever provider actually answered."""

from __future__ import annotations

import pytest

from app.providers.base import (
    AllProvidersUnavailable,
    CompletionRequest,
    CompletionResult,
    LLMProvider,
    ProviderAuthError,
    ProviderError,
    ProviderTimeoutError,
    RateLimitError,
)
from app.providers.fallback import FallbackLLMProvider

_REQ = CompletionRequest(system="s", user="u")


class _Stub(LLMProvider):
    def __init__(self, name: str, *, error: Exception | None = None) -> None:
        self.name = name
        self._error = error
        self.calls = 0
        self.closed = False

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return CompletionResult(text="{}", model=f"{self.name}-1", provider=self.name)

    async def health_check(self) -> bool:
        if self._error is not None:
            raise ProviderError(f"{self.name} down")
        return True

    async def aclose(self) -> None:
        self.closed = True


async def test_primary_success_never_touches_secondary() -> None:
    primary, secondary = _Stub("groq"), _Stub("ollama")
    fb = FallbackLLMProvider(primary, secondary)

    result = await fb.complete(_REQ)

    assert result.provider == "groq"
    assert secondary.calls == 0


@pytest.mark.parametrize(
    "error",
    [
        RateLimitError("429"),
        ProviderTimeoutError("timed out"),
        ProviderAuthError("401"),
        ProviderError("groq transport error: connection reset"),
    ],
)
async def test_failover_to_secondary_and_tag_it(error: Exception) -> None:
    primary = _Stub("groq", error=error)
    secondary = _Stub("ollama")
    fb = FallbackLLMProvider(primary, secondary)

    result = await fb.complete(_REQ)

    assert result.provider == "ollama"
    assert primary.calls == 1 and secondary.calls == 1


async def test_a_non_transport_provider_error_is_not_a_failover() -> None:
    primary = _Stub("groq", error=ProviderError("groq malformed response: {}"))
    secondary = _Stub("ollama")
    fb = FallbackLLMProvider(primary, secondary)

    with pytest.raises(ProviderError, match="malformed"):
        await fb.complete(_REQ)
    assert secondary.calls == 0


async def test_both_failing_raises_all_providers_unavailable() -> None:
    fb = FallbackLLMProvider(
        _Stub("groq", error=RateLimitError("429")),
        _Stub("ollama", error=ProviderError("ollama transport error: refused")),
    )
    with pytest.raises(AllProvidersUnavailable, match="groq failed .* ollama failed"):
        await fb.complete(_REQ)


async def test_health_check_passes_if_either_provider_is_up() -> None:
    fb = FallbackLLMProvider(_Stub("groq", error=RateLimitError("x")), _Stub("ollama"))
    assert await fb.health_check() is True


async def test_aclose_closes_both() -> None:
    primary, secondary = _Stub("groq"), _Stub("ollama")
    await FallbackLLMProvider(primary, secondary).aclose()
    assert primary.closed and secondary.closed


def test_name_reports_the_chain() -> None:
    assert FallbackLLMProvider(_Stub("groq"), _Stub("ollama")).name == "groq->ollama"

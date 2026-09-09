"""Primary/secondary LLM provider with automatic failover.

The pipeline holds one ``LLMProvider``. Wrapping two of them here keeps the
failover invisible to every call site: ``complete()`` tries the primary, and on
a rate limit, timeout, auth rejection, or transport error it retries the same
request on the secondary. The returned ``CompletionResult.provider`` always names
whichever provider actually served the call, so downstream code can tag each
fact with its real source.
"""

from __future__ import annotations

import logging

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

logger = logging.getLogger(__name__)

# Failures that mean "this provider cannot serve the call right now" — a
# different provider may still succeed. A malformed response or a rejected
# output schema is NOT here: switching providers would only hide a real bug.
_FAILOVER_ERRORS: tuple[type[ProviderError], ...] = (
    RateLimitError,
    ProviderTimeoutError,
    ProviderAuthError,
)


def _is_transport_error(exc: ProviderError) -> bool:
    return type(exc) is ProviderError and "transport error" in str(exc)


class FallbackLLMProvider(LLMProvider):
    name = "fallback"

    def __init__(self, primary: LLMProvider, secondary: LLMProvider) -> None:
        self._primary = primary
        self._secondary = secondary
        self.name = f"{primary.name}->{secondary.name}"

    @property
    def providers(self) -> tuple[LLMProvider, LLMProvider]:
        return (self._primary, self._secondary)

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        try:
            return await self._primary.complete(request)
        except _FAILOVER_ERRORS as exc:
            reason = type(exc).__name__
        except ProviderError as exc:
            if not _is_transport_error(exc):
                raise
            reason = "transport error"

        logger.warning(
            "primary provider %s unavailable (%s); falling back to %s",
            self._primary.name,
            reason,
            self._secondary.name,
        )
        try:
            return await self._secondary.complete(request)
        except ProviderError as exc:
            raise AllProvidersUnavailable(
                f"{self._primary.name} failed ({reason}) and "
                f"{self._secondary.name} failed ({exc})"
            ) from exc

    async def health_check(self) -> bool:
        for provider in self.providers:
            try:
                if await provider.health_check():
                    return True
            except ProviderError:
                continue
        raise ProviderError(f"no provider in {self.name} is reachable")

    async def aclose(self) -> None:
        for provider in self.providers:
            await provider.aclose()

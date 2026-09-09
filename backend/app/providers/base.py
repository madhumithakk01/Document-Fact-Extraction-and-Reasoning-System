"""Interfaces shared by every provider implementation.

``LLMProvider`` covers the three reasoning calls the pipeline makes -- extraction,
verification, and adjudication -- all of which reduce to a single schema-constrained
completion primitive. ``EmbeddingProvider`` is always satisfied locally; embeddings
are the highest-frequency call in the system and must never be rate-limited.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


class ProviderError(RuntimeError):
    """Raised when a provider call fails in a way the caller should handle
    (transport error, auth failure, malformed response)."""


class RateLimitError(ProviderError):
    """The provider is rate limited or out of quota, and its own retry budget is
    spent. A different provider may still succeed."""


class ProviderTimeoutError(ProviderError):
    """The provider did not respond within the configured timeout."""


class ProviderAuthError(ProviderError):
    """The provider rejected the credentials (401/403). Surfaced as a distinct
    type so a fallback path can try the next provider instead of failing hard."""


class AllProvidersUnavailable(ProviderError):
    """Every provider in a fallback chain failed to serve a call."""


@dataclass(slots=True)
class CompletionRequest:
    """A single reasoning call.

    ``json_schema``, when set, constrains the model to structured output matching
    that JSON Schema. Callers that need a fact record back always set it.
    """

    system: str
    user: str
    json_schema: dict[str, Any] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    stop: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CompletionResult:
    text: str
    model: str
    provider: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None

    def json(self) -> Any:
        """Parse ``text`` as JSON. Raises ``ProviderError`` if it is not valid
        JSON -- used by callers that sent a ``json_schema``."""
        import json

        try:
            return json.loads(self.text)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise ProviderError(f"expected JSON completion, got: {self.text[:200]!r}") from exc


class LLMProvider(abc.ABC):
    """Reasoning-call interface. Concrete providers differ only in transport."""

    name: str

    @abc.abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResult:
        """Run one completion. Deterministic by default (temperature 0)."""

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """Trivial round-trip call used to prove a provider is reachable and
        configured. Returns True on success, raises ``ProviderError`` otherwise."""

    async def aclose(self) -> None:  # noqa: B027 - optional hook, no-op by default
        """Release transport resources. Overridden by HTTP-backed providers."""
        return None


class EmbeddingProvider(abc.ABC):
    """Local embedding interface. One vector per fact, never provider-gated."""

    name: str
    dimension: int

    @abc.abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Order of the returned vectors matches input."""

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]

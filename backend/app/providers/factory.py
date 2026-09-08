"""Construct providers from configuration.

``get_llm_provider`` is the only place that maps ``LLM_PROVIDER`` to a concrete
class. Both accessors are cached so the embedding model and HTTP clients are
created once per process.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import ProviderName, Settings, get_settings
from app.providers.base import EmbeddingProvider, LLMProvider, ProviderError
from app.providers.local_embeddings import LocalEmbeddingProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai_compatible import OpenAICompatibleProvider


def build_llm_provider(settings: Settings) -> LLMProvider:
    common = {
        "default_temperature": settings.llm_temperature,
        "default_max_tokens": settings.llm_max_tokens,
        "timeout_seconds": settings.llm_timeout_seconds,
    }
    openai_common = {
        **common,
        "max_concurrency": settings.llm_max_concurrency,
        "min_request_interval": settings.llm_min_request_interval,
    }
    if settings.llm_provider is ProviderName.groq:
        return OpenAICompatibleProvider(
            name="groq",
            base_url=settings.groq_base_url,
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            **openai_common,
        )
    if settings.llm_provider is ProviderName.frontier:
        return OpenAICompatibleProvider(
            name="frontier",
            base_url=settings.frontier_base_url,
            api_key=settings.frontier_api_key,
            model=settings.frontier_model,
            **openai_common,
        )
    if settings.llm_provider is ProviderName.ollama:
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            **common,
        )
    raise ProviderError(f"unknown LLM provider: {settings.llm_provider!r}")


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Process-wide singleton. Shared across every request and background task;
    its transport is closed once in the app's lifespan shutdown, never by a
    per-request or per-document caller."""
    return build_llm_provider(get_settings())


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    return LocalEmbeddingProvider(
        model_name=settings.embedding_model,
        device=settings.embedding_device,
    )

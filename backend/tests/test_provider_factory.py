from __future__ import annotations

import pytest

from app.config import Settings
from app.providers.base import ProviderError
from app.providers.factory import build_llm_provider
from app.providers.fallback import FallbackLLMProvider
from app.providers.local_embeddings import LocalEmbeddingProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai_compatible import OpenAICompatibleProvider


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_groq_selected_when_key_present() -> None:
    provider = build_llm_provider(_settings(llm_provider="groq", groq_api_key="test-key"))
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.name == "groq"


def test_groq_without_key_raises() -> None:
    with pytest.raises(ProviderError, match="no API key"):
        build_llm_provider(_settings(llm_provider="groq", groq_api_key=""))


def test_frontier_selected_and_isolated_from_groq() -> None:
    provider = build_llm_provider(
        _settings(llm_provider="frontier", frontier_api_key="k", frontier_model="gpt-4o")
    )
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.name == "frontier"


def test_ollama_selected_without_any_key() -> None:
    provider = build_llm_provider(_settings(llm_provider="ollama"))
    assert isinstance(provider, OllamaProvider)
    assert provider.name == "ollama"


def test_swap_is_config_only() -> None:
    """The same call site yields a different transport purely from settings."""
    groq = build_llm_provider(_settings(llm_provider="groq", groq_api_key="k"))
    ollama = build_llm_provider(_settings(llm_provider="ollama"))
    assert type(groq) is not type(ollama)
    assert isinstance(groq, OpenAICompatibleProvider)
    assert isinstance(ollama, OllamaProvider)


def test_fallback_wraps_primary_and_secondary_when_configured() -> None:
    provider = build_llm_provider(
        _settings(
            llm_provider="groq",
            groq_api_key="k",
            llm_fallback_provider="ollama",
        )
    )
    assert isinstance(provider, FallbackLLMProvider)
    primary, secondary = provider.providers
    assert isinstance(primary, OpenAICompatibleProvider) and primary.name == "groq"
    assert isinstance(secondary, OllamaProvider)


def test_no_fallback_when_unset_or_same_as_primary() -> None:
    plain = build_llm_provider(_settings(llm_provider="groq", groq_api_key="k"))
    assert isinstance(plain, OpenAICompatibleProvider)

    same = build_llm_provider(
        _settings(llm_provider="groq", groq_api_key="k", llm_fallback_provider="groq")
    )
    assert isinstance(same, OpenAICompatibleProvider)


def test_local_embedding_provider_reports_known_dimension() -> None:
    provider = LocalEmbeddingProvider(model_name="BAAI/bge-small-en-v1.5", device="cpu")
    assert provider.dimension == 384
    assert provider.name == "sentence-transformers"

from __future__ import annotations

from app.config import ProviderName, Settings


def test_defaults_select_groq_and_local_embeddings() -> None:
    settings = Settings(_env_file=None)
    assert settings.llm_provider is ProviderName.groq
    assert settings.embedding_model.startswith("BAAI/") or "nomic" in settings.embedding_model
    assert settings.llm_temperature == 0.0


def test_provider_can_be_switched_by_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    settings = Settings(_env_file=None)
    assert settings.llm_provider is ProviderName.ollama

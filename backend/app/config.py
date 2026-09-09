"""Runtime configuration, loaded from environment / .env.

Nothing in the pipeline reads os.environ directly; everything comes through
``get_settings()`` so provider and storage choices are a config change only.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderName(StrEnum):
    groq = "groq"
    ollama = "ollama"
    frontier = "frontier"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://factlayer:factlayer@localhost:5432/factlayer"

    llm_provider: ProviderName = ProviderName.groq
    # when set (and different from llm_provider), reasoning calls fail over to
    # this provider on a rate limit, timeout, auth rejection, or transport error
    llm_fallback_provider: ProviderName | None = None

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    frontier_api_key: str = ""
    frontier_model: str = "gpt-4o"
    frontier_base_url: str = "https://api.openai.com/v1"

    llm_temperature: float = 0.0
    llm_max_tokens: int = 6000
    llm_timeout_seconds: float = 90.0
    # keep within a free tokens-per-minute budget: at most this many in-flight
    # provider requests, spaced at least this many seconds apart
    llm_max_concurrency: int = 1
    llm_min_request_interval: float = 2.0

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_device: str = "cpu"

    upload_dir: str = "./storage/uploads"
    page_image_dir: str = "./storage/page_images"

    @field_validator("llm_fallback_provider", mode="before")
    @classmethod
    def _blank_fallback_is_none(cls, v: object) -> object:
        # an unset env var arrives as "" -- treat it as "no fallback", not an
        # invalid enum value
        if isinstance(v, str) and not v.strip():
            return None
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()

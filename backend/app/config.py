"""Runtime configuration, loaded from environment / .env.

Nothing in the pipeline reads os.environ directly; everything comes through
``get_settings()`` so provider and storage choices are a config change only.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

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


@lru_cache
def get_settings() -> Settings:
    return Settings()

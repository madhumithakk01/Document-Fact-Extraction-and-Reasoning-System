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


class DualExtractMode(StrEnum):
    off = "off"
    demo_only = "demo_only"  # only the lowest-confidence facts, plus any matched by name
    all = "all"


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

    # independent dual-extraction corroboration: re-run the extraction prompt on a
    # second provider and reconcile through the deterministic precheck instead of
    # relying on one model checking itself.
    dual_extract_mode: DualExtractMode = DualExtractMode.demo_only
    dual_extract_provider: ProviderName = ProviderName.ollama
    # a small local model re-extracting a page is slower than the hosted primary
    dual_extract_timeout_seconds: float = 240.0
    # in demo_only mode, corroborate at most this many facts per document (the
    # lowest-confidence ones first)
    dual_extract_limit: int = 5
    # case-insensitive substrings; any fact whose entity or attribute matches is
    # always corroborated, regardless of mode's limit
    dual_extract_match: list[str] = []

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

    @field_validator("dual_extract_mode", mode="before")
    @classmethod
    def _blank_mode_is_default(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return DualExtractMode.demo_only
        return v

    @field_validator("dual_extract_match", mode="before")
    @classmethod
    def _split_match_list(cls, v: object) -> object:
        # accept a comma-separated env string; "" means no matches
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()

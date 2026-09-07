"""Shared skip guards for tests that need a live database or LLM provider."""

from __future__ import annotations

import asyncio
import urllib.request

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings


def provider_available() -> bool:
    """A provider is usable if it is configured (via .env) or Ollama answers."""
    settings = get_settings()
    if settings.llm_provider.value == "groq" and settings.groq_api_key:
        return True
    if settings.llm_provider.value == "frontier" and settings.frontier_api_key:
        return True
    try:
        urllib.request.urlopen(f"{settings.ollama_base_url}/api/tags", timeout=1)
        return True
    except Exception:
        return False


def db_reachable() -> bool:
    async def _check() -> bool:
        engine = create_async_engine(get_settings().database_url)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1 FROM projects LIMIT 0"))
            return True
        except Exception:
            return False
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_check())
    except RuntimeError:  # pragma: no cover - running loop, assume available
        return True

from __future__ import annotations

import pytest

from app.config import get_settings
from app.providers.factory import get_embedding_provider, get_llm_provider


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    """Settings and providers are process-cached; reset them around every test
    so env overrides take effect in isolation."""
    for cached in (get_settings, get_llm_provider, get_embedding_provider):
        cached.cache_clear()
    yield
    for cached in (get_settings, get_llm_provider, get_embedding_provider):
        cached.cache_clear()


@pytest.fixture(autouse=True)
def _dual_extract_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dual-extraction corroboration re-runs extraction on a second provider over
    the network. Keep it off unless a test explicitly opts in."""
    monkeypatch.setenv("DUAL_EXTRACT_MODE", "off")
    get_settings.cache_clear()

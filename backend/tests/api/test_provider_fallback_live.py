"""PHASE 6 exit criterion: with Groq unusable, the whole pipeline still runs
via the local Ollama fallback, and every fact is tagged provider_used='ollama'.

Needs a reachable database and a running Ollama with the configured model pulled.
"""

from __future__ import annotations

import urllib.request

import pytest

from app.config import get_settings
from app.providers.factory import get_llm_provider
from tests.api.conftest import requires_db


def _ollama_up() -> bool:
    try:
        urllib.request.urlopen(
            f"{get_settings().ollama_base_url}/api/tags", timeout=1
        )
        return True
    except Exception:
        return False


pytestmark = [
    pytest.mark.slow,
    requires_db,
    pytest.mark.skipif(not _ollama_up(), reason="Ollama not reachable"),
]


def test_bad_groq_key_falls_back_to_ollama_end_to_end(client, tiny_pdf, monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "BAD_KEY_TO_FORCE_401")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "ollama")
    get_settings.cache_clear()
    get_llm_provider.cache_clear()

    pid = client.post("/projects", json={"name": "fallback-live"}).json()["project_id"]
    up = client.post(
        f"/projects/{pid}/documents",
        files={"file": ("acme.pdf", tiny_pdf, "application/pdf")},
    )
    assert up.status_code == 202
    did = up.json()["document_id"]

    status = client.get(f"/projects/{pid}/documents/{did}/status").json()
    assert status["processing_status"] == "ready", status
    assert status["fact_count"] > 0

    facts = client.get(f"/projects/{pid}/facts").json()
    assert facts
    assert {f["provider_used"] for f in facts} == {"ollama"}

    client.delete(f"/projects/{pid}/documents/{did}")
    client.delete(f"/projects/{pid}")

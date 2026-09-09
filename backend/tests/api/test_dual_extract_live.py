"""PHASE 7 exit criterion: for a real document, a fact carries a primary
extraction (Groq), a blind independent extraction (Ollama), an agreement verdict
from the deterministic precheck, and the resulting confidence -- end to end.

Needs a database, a working Groq key, and a running Ollama with the model pulled.
"""

from __future__ import annotations

import urllib.request

import pytest

from app.config import get_settings
from app.providers.factory import get_llm_provider
from app.verification.dual_extract import _score
from tests.api.conftest import requires_db, requires_provider


def _ollama_up() -> bool:
    try:
        urllib.request.urlopen(f"{get_settings().ollama_base_url}/api/tags", timeout=1)
        return True
    except Exception:
        return False


pytestmark = [
    pytest.mark.slow,
    requires_db,
    requires_provider,
    pytest.mark.skipif(not _ollama_up(), reason="Ollama not reachable"),
]

_CORROBORATED = _score(True, [])
_UNCONFIRMED = _score(False, [])


def test_groq_primary_ollama_blind_corroboration_end_to_end(
    client, tiny_pdf, monkeypatch
) -> None:
    monkeypatch.setenv("DUAL_EXTRACT_MODE", "all")
    monkeypatch.setenv("DUAL_EXTRACT_PROVIDER", "ollama")
    get_settings.cache_clear()
    get_llm_provider.cache_clear()

    pid = client.post("/projects", json={"name": "dual-extract-live"}).json()["project_id"]
    up = client.post(
        f"/projects/{pid}/documents",
        files={"file": ("acme.pdf", tiny_pdf, "application/pdf")},
    )
    assert up.status_code == 202
    did = up.json()["document_id"]

    status = client.get(f"/projects/{pid}/documents/{did}/status").json()
    assert status["processing_status"] == "ready", status

    facts = client.get(f"/projects/{pid}/facts").json()
    assert facts

    corroborated = [f for f in facts if f["corroboration"]]
    assert corroborated, "every extracted fact should carry a corroboration verdict"

    for f in corroborated:
        c = f["corroboration"]
        assert c["blind_provider"] == "ollama"
        assert c["status"] in ("independently_corroborated", "single_source_unconfirmed")
        expected = _CORROBORATED if c["status"] == "independently_corroborated" else _UNCONFIRMED
        # the score (minus any assumed-flag penalty) replaces the flat verifier value
        assert 0.05 <= f["verifier_confidence"] <= expected + 1e-9
        if c["status"] == "single_source_unconfirmed":
            assert c["needs_human_review"] is True

    agreed = [
        f
        for f in corroborated
        if f["corroboration"]["status"] == "independently_corroborated"
    ]
    assert agreed, "expected at least one fact both providers independently extracted"
    assert agreed[0]["corroboration"]["corroborating_provider"] == "ollama"

    client.delete(f"/projects/{pid}/documents/{did}")
    client.delete(f"/projects/{pid}")

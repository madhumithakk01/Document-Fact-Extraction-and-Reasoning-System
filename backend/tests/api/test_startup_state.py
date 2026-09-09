"""Guards on the default run path: the app opens empty and never auto-loads
the curated snapshot.

``scripts.seed`` and ``seed/snapshot.json`` are dev-only tooling. If anything in
the app's import graph, lifespan, or a router pulled the loader in, a fresh start
could serve a hand-authored snapshot as if it were live pipeline output.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from tests.api.conftest import requires_db


def test_importing_the_app_does_not_import_the_seed_loader() -> None:
    code = (
        "import sys, app.main\n"
        "seeded = sorted(m for m in sys.modules if m.startswith('scripts.seed'))\n"
        "assert not seeded, seeded\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=".",
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.slow
@requires_db
def test_a_fresh_project_has_no_documents_or_facts(client) -> None:
    pid = client.post("/projects", json={"name": "startup-empty-state"}).json()["project_id"]
    try:
        summary = client.get(f"/projects/{pid}").json()
        assert summary["document_count"] == 0
        assert summary["fact_count"] == 0
        assert client.get(f"/projects/{pid}/facts").json() == []
        assert client.get(f"/projects/{pid}/documents").json() == []
        assert client.get(f"/projects/{pid}/relationships").json() == []
    finally:
        client.delete(f"/projects/{pid}")

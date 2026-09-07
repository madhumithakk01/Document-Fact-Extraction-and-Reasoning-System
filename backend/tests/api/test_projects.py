from __future__ import annotations

import uuid

import pytest

from tests.api.conftest import requires_db

pytestmark = [pytest.mark.slow, requires_db]


def _new_project(client, name="api-test") -> str:
    r = client.post("/projects", json={"name": name})
    assert r.status_code == 201
    return r.json()["project_id"]


def test_create_list_and_get_project(client) -> None:
    pid = _new_project(client, "api-test-crud")
    try:
        assert any(p["project_id"] == pid for p in client.get("/projects").json())

        summary = client.get(f"/projects/{pid}").json()
        assert summary["name"] == "api-test-crud"
        assert summary["document_count"] == 0
        assert summary["fact_count"] == 0
        assert "domain_profile" in summary
    finally:
        # projects have no delete endpoint; leave it, the name is namespaced
        pass


def test_missing_project_is_404(client) -> None:
    assert client.get(f"/projects/{uuid.uuid4()}").status_code == 404
    assert client.get(f"/projects/{uuid.uuid4()}/facts").status_code == 404
    assert client.get(f"/projects/{uuid.uuid4()}/documents").status_code == 404


def test_reject_blank_project_name(client) -> None:
    assert client.post("/projects", json={"name": ""}).status_code == 422

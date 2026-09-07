"""The Phase 7 exit criterion: the whole pipeline is drivable from the API alone.

Uploads a small PDF, waits for background processing, then reads facts,
relationships, evidence, ontology, and evaluation entirely over HTTP.
"""

from __future__ import annotations

import pytest

from tests.api.conftest import requires_db, requires_provider

pytestmark = [pytest.mark.slow, requires_db, requires_provider]


def test_upload_process_and_read_everything_over_http(client, tiny_pdf) -> None:
    pid = client.post("/projects", json={"name": "api-e2e"}).json()["project_id"]

    # upload -> 202 + queued
    up = client.post(
        f"/projects/{pid}/documents",
        files={"file": ("acme.pdf", tiny_pdf, "application/pdf")},
    )
    assert up.status_code == 202
    did = up.json()["document_id"]
    assert up.json()["processing_status"] in ("queued", "extracting")

    # TestClient runs the background task before returning, so it is done now
    status = client.get(f"/projects/{pid}/documents/{did}/status").json()
    assert status["processing_status"] == "ready", status
    assert status["fact_count"] > 0
    assert status["chunk_count"] >= 2

    # documents list + detail
    docs = client.get(f"/projects/{pid}/documents").json()
    assert len(docs) == 1 and docs[0]["document_id"] == did
    assert client.get(f"/projects/{pid}/documents/{did}").json()["page_count"] == 2

    # facts, with filtering
    facts = client.get(f"/projects/{pid}/facts").json()
    assert facts, "expected facts extracted from the PDF"
    verified = client.get(
        f"/projects/{pid}/facts", params={"verification_status": "verified"}
    ).json()
    assert all(f["verification_status"] == "verified" for f in verified)

    fact = facts[0]
    one = client.get(f"/projects/{pid}/facts/{fact['fact_id']}").json()
    assert one["fact_id"] == fact["fact_id"]

    # evidence view resolves the span and (usually) a bbox
    ev = client.get(f"/projects/{pid}/facts/{fact['fact_id']}/evidence").json()
    assert ev["evidence_text"]
    assert ev["surrounding_text"]
    assert ev["page_number"] in (1, 2)

    # relationships: the two pages state the same EBITDA and revenue differently
    rels = client.get(f"/projects/{pid}/relationships").json()
    assert isinstance(rels, list)
    if rels:
        detail = client.get(f"/projects/{pid}/relationships/{rels[0]['relationship_id']}").json()
        assert "fact_a" in detail and "fact_b" in detail
        assert detail["relationship_type"] in (
            "corroborates",
            "contradicts",
            "reconciled_by_context",
            "unrelated",
        )

    # ontology + evaluation are live reads
    ontology = client.get(f"/projects/{pid}/ontology").json()
    assert "groups" in ontology
    evaluation = client.get(f"/projects/{pid}/evaluation").json()
    assert evaluation["grounding_pass_rate"] >= 0.0
    assert sum(evaluation["facts_by_status"].values()) == len(facts)

    # reasoning console answers from this project's facts
    q = client.post(
        f"/projects/{pid}/query",
        json={"question": "What was FY24 EBITDA?"},
    )
    assert q.status_code == 200
    body = q.json()
    assert "answer" in body and isinstance(body["citations"], list)
    assert isinstance(body["trace"], list)

    # delete removes the document and cascades its facts/relationships
    assert client.delete(f"/projects/{pid}/documents/{did}").status_code == 204
    assert client.get(f"/projects/{pid}/documents/{did}").status_code == 404
    assert client.get(f"/projects/{pid}/facts").json() == []

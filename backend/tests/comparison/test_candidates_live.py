"""Live pgvector candidate generation."""

from __future__ import annotations

import pytest

from app.comparison.candidates import candidates_for_fact
from app.comparison.embedding import embed_missing_facts
from app.repository import create_project, delete_project
from tests.comparison.conftest import make_document, make_fact

pytestmark = pytest.mark.slow


async def test_nearest_neighbours_are_same_kind_same_project_not_self(db_session) -> None:
    proj = await create_project(db_session, "cand-test")
    other = await create_project(db_session, "cand-test-other")
    try:
        doc = make_document(proj.project_id)
        doc_other = make_document(other.project_id)
        db_session.add_all([doc, doc_other])
        await db_session.flush()

        target = make_fact(
            proj.project_id,
            doc.document_id,
            entity="Delhivery",
            attribute="FY24 consolidated EBITDA",
            value={"comparator": "eq", "number": 127, "unit": "INR Crore"},
            period="FY24",
        )
        near = make_fact(
            proj.project_id,
            doc.document_id,
            entity="Delhivery",
            attribute="EBITDA (consolidated) FY24",
            value={"comparator": "eq", "number": 1266, "unit": "INR million"},
            period="FY2023-24",
        )
        far = make_fact(
            proj.project_id,
            doc.document_id,
            entity="Delhivery",
            attribute="number of delivery hubs",
            value={"comparator": "eq", "number": 5000, "unit": "hubs"},
            period="FY24",
        )
        wrong_kind = make_fact(
            proj.project_id,
            doc.document_id,
            entity="Delhivery",
            attribute="FY24 consolidated EBITDA",
            value={"state": "profitable"},
            period="FY24",
            fact_kind="status",
        )
        cross_project = make_fact(
            other.project_id,
            doc_other.document_id,
            entity="Delhivery",
            attribute="FY24 consolidated EBITDA",
            value={"comparator": "eq", "number": 127, "unit": "INR Crore"},
            period="FY24",
        )
        pending = make_fact(
            proj.project_id,
            doc.document_id,
            entity="Delhivery",
            attribute="FY24 consolidated EBITDA margin",
            value={"comparator": "eq", "number": 1.6, "unit": "%"},
            period="FY24",
            status="pending",
        )
        db_session.add_all([target, near, far, wrong_kind, cross_project, pending])
        await db_session.flush()

        n = await embed_missing_facts(db_session, proj.project_id)
        assert n >= 4
        await embed_missing_facts(db_session, other.project_id)

        cands = await candidates_for_fact(db_session, proj.project_id, target, k=10)
        ids = {c.fact.fact_id for c in cands}

        assert near.fact_id in ids
        assert target.fact_id not in ids  # never itself
        assert wrong_kind.fact_id not in ids  # different fact_kind
        assert cross_project.fact_id not in ids  # different project
        assert pending.fact_id not in ids  # not usable
        # results are ordered by cosine distance
        dists = [c.cosine_distance for c in cands]
        assert dists == sorted(dists)
    finally:
        await db_session.rollback()
        for pid in (proj.project_id, other.project_id):
            await delete_project(db_session, pid)
        await db_session.commit()

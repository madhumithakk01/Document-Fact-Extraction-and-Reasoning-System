"""Live cross-project isolation test against a real Postgres.

Skipped unless DATABASE_URL points at a reachable database with the schema
migrated (``docker compose up -d db`` then ``python -m scripts.db upgrade``).
Creates two projects with deliberately overlapping content and shows that
neither one can see the other's rows, and that deleting one leaves the other
intact.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.document import Document
from app.models.fact import Fact
from app.repository import (
    ProjectScope,
    create_project,
    delete_project,
    get_fact,
    list_documents,
    list_facts,
)
from app.repository.facts import count_facts_by_status


async def _db_reachable() -> bool:
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1 FROM projects LIMIT 0"))
        return True
    except Exception:
        return False
    finally:
        await engine.dispose()


pytestmark = pytest.mark.slow


@pytest.fixture
async def session() -> AsyncSession:
    if not await _db_reachable():
        pytest.skip("DATABASE_URL not reachable or schema not migrated")
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
    await engine.dispose()


def _fact(project_id: uuid.UUID, document_id: uuid.UUID, entity: str, status: str) -> Fact:
    return Fact(
        fact_id=uuid.uuid4(),
        project_id=project_id,
        document_id=document_id,
        source_anchor={},
        fact_kind="quantitative",
        entity=entity,
        attribute="revenue",
        value={"comparator": "eq", "number": 100.0},
        period={"raw_label": "FY24"},
        qualifiers={},
        evidence_text=f"{entity} revenue was 100 in FY24",
        verification_status=status,
        extraction_confidence=0.9,
        notes=[],
    )


def _doc(project_id: uuid.UUID, name: str) -> Document:
    return Document(
        document_id=uuid.uuid4(),
        project_id=project_id,
        filename=name,
        content_hash=uuid.uuid4().hex,
        byte_size=1,
        content_type_detected="text_native",
        processing_status="ready",
        page_count=1,
    )


async def test_two_projects_with_overlapping_content_never_leak(session: AsyncSession) -> None:
    proj_a = await create_project(session, "iso-test-A")
    proj_b = await create_project(session, "iso-test-B")
    scope_a = ProjectScope(project_id=proj_a.project_id, session=session)
    scope_b = ProjectScope(project_id=proj_b.project_id, session=session)

    try:
        doc_a = _doc(proj_a.project_id, "a.pdf")
        doc_b = _doc(proj_b.project_id, "b.pdf")
        session.add_all([doc_a, doc_b])
        await session.flush()

        a_facts = [
            _fact(proj_a.project_id, doc_a.document_id, "Delhivery", "verified"),
            _fact(proj_a.project_id, doc_a.document_id, "RBI", "needs_review"),
        ]
        b_facts = [
            _fact(proj_b.project_id, doc_b.document_id, "Delhivery", "verified"),
            _fact(proj_b.project_id, doc_b.document_id, "IMF", "verified"),
        ]
        session.add_all([*a_facts, *b_facts])
        await session.flush()

        # each scope sees only its own facts
        seen_a = {f.fact_id for f in await list_facts(scope_a)}
        seen_b = {f.fact_id for f in await list_facts(scope_b)}
        assert seen_a == {f.fact_id for f in a_facts}
        assert seen_b == {f.fact_id for f in b_facts}
        assert seen_a.isdisjoint(seen_b)

        # the shared entity name does not bridge the projects
        shared = await list_facts(scope_a, entity="Delhivery")
        assert [f.project_id for f in shared] == [proj_a.project_id]

        # a fact id from A is invisible through B's scope
        assert await get_fact(scope_b, a_facts[0].fact_id) is None
        assert await get_fact(scope_a, a_facts[0].fact_id) is not None

        # documents and status counts are likewise scoped
        assert {d.document_id for d in await list_documents(scope_a)} == {doc_a.document_id}
        assert await count_facts_by_status(scope_a) == {"verified": 1, "needs_review": 1}

        # deleting A cascades and leaves B whole
        await delete_project(session, proj_a.project_id)
        await session.flush()
        assert await list_facts(scope_a) == []
        assert {f.fact_id for f in await list_facts(scope_b)} == {f.fact_id for f in b_facts}
    finally:
        await session.rollback()
        for pid in (proj_a.project_id, proj_b.project_id):
            await delete_project(session, pid)
        await session.commit()

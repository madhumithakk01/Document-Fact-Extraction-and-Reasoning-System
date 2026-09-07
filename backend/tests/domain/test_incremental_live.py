"""The Phase 9 exit criterion: adding a 4th document does not reprocess or
re-embed the first three."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.comparison.embedding import embed_missing_facts
from app.config import get_settings
from app.domain import DomainProfile, profile_new_document
from app.models.document import Document
from app.models.fact import Fact
from app.models.project import Project
from app.repository import create_project, delete_project
from tests._env import db_reachable
from tests.comparison.conftest import make_document, make_fact

pytestmark = [pytest.mark.slow, pytest.mark.skipif(not db_reachable(), reason="no database")]


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
    await engine.dispose()


LOGISTICS = [
    "Delhivery FY24 consolidated revenue was INR 8,142 crore across express and PTL.",
    "Delhivery FY24 EBITDA reached INR 127 crore; express parcel volumes grew.",
    "Delhivery operated a nationwide network of hubs and gateways during FY24.",
    "Delhivery FY24 PAT loss narrowed; adjusted EBITDA margin improved.",
]
MACRO = "India's real GDP growth for 2025-26 is projected at 6.5 per cent by the central bank."


async def _add_document(
    session: AsyncSession, project_id: uuid.UUID, text: str, n_facts: int = 2
) -> uuid.UUID:
    doc = make_document(project_id, f"doc-{uuid.uuid4().hex[:6]}.pdf")
    session.add(doc)
    await session.flush()
    for i in range(n_facts):
        session.add(
            make_fact(
                project_id,
                doc.document_id,
                entity="Delhivery",
                attribute=f"metric {i}",
                value={"comparator": "eq", "number": 100 + i},
                period="FY24",
                evidence=text,
            )
        )
    await session.flush()
    await profile_new_document(session, project_id, doc.document_id, [text])
    return doc.document_id


async def test_fourth_document_does_not_re_embed_the_first_three(session: AsyncSession) -> None:
    project = await create_project(session, "incremental-test")
    pid = project.project_id
    try:
        doc_ids = []
        for text in LOGISTICS[:3]:
            doc_ids.append(await _add_document(session, pid, text))
        await session.commit()

        # embed the facts of the first three documents
        await embed_missing_facts(session, pid)
        await session.commit()

        before = {
            r.fact_id: list(r.embedding)
            for r in (
                await session.execute(
                    select(Fact).where(Fact.project_id == pid, Fact.embedding.is_not(None))
                )
            )
            .scalars()
            .all()
        }
        assert len(before) == 6
        profile3 = DomainProfile.load((await session.get(Project, pid)).domain_profile)
        assert profile3.document_count == 3
        assert len(profile3.sub_clusters) == 1

        # add the 4th (same domain)
        d4 = await _add_document(session, pid, LOGISTICS[3])
        await embed_missing_facts(session, pid)
        await session.commit()

        after = {
            r.fact_id: list(r.embedding)
            for r in (
                await session.execute(
                    select(Fact).where(Fact.project_id == pid, Fact.fact_id.in_(list(before)))
                )
            )
            .scalars()
            .all()
        }
        # every earlier fact keeps the exact vector it already had
        assert after == before

        profile4 = DomainProfile.load((await session.get(Project, pid)).domain_profile)
        assert profile4.document_count == 4
        assert len(profile4.sub_clusters) == 1
        assert str(d4) in profile4.sub_clusters[0].document_ids

        d4_row = await session.get(Document, d4)
        assert d4_row.off_domain is False
        assert d4_row.sub_cluster_id == "sc_1"

        # add an off-topic 5th document -> new sub-cluster, soft signal
        d5 = await _add_document(session, pid, MACRO)
        await session.commit()
        d5_row = await session.get(Document, d5)
        assert d5_row.off_domain is True
        assert d5_row.sub_cluster_id == "sc_2"
        profile5 = DomainProfile.load((await session.get(Project, pid)).domain_profile)
        assert profile5.document_count == 5
        assert len(profile5.sub_clusters) == 2
    finally:
        await session.rollback()
        await delete_project(session, pid)
        await session.commit()

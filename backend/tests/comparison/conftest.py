"""Shared live-DB fixtures for comparison integration tests."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.document import Document
from app.models.fact import Fact


async def _db_reachable() -> bool:
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1 FROM facts LIMIT 0"))
        return True
    except Exception:
        return False
    finally:
        await engine.dispose()


@pytest.fixture
async def db_session() -> AsyncSession:
    if not await _db_reachable():
        pytest.skip("DATABASE_URL not reachable or schema not migrated")
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
    await engine.dispose()


def make_document(project_id: uuid.UUID, name: str = "doc.pdf") -> Document:
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


def make_fact(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    entity: str,
    attribute: str,
    value: dict,
    period: str,
    qualifiers: dict | None = None,
    fact_kind: str = "quantitative",
    status: str = "verified",
    evidence: str = "evidence text",
    page: int = 1,
) -> Fact:
    return Fact(
        fact_id=uuid.uuid4(),
        project_id=project_id,
        document_id=document_id,
        source_anchor={},
        page_number=page,
        fact_kind=fact_kind,
        entity=entity,
        attribute=attribute,
        value=value,
        period={"raw_label": period},
        qualifiers=qualifiers or {},
        evidence_text=evidence,
        verification_status=status,
        extraction_confidence=0.9,
        verifier_confidence=0.9,
        notes=[],
    )

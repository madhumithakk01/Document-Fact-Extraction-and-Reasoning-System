"""Genuine generalization test: a macro-economic document (a domain the pipeline
was never tuned against) run end to end -- ingest, extract, verify, compare --
and checked for plausible, well-formed facts."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.comparison.pipeline import compare_document
from app.config import get_settings
from app.extraction import extract_document
from app.extraction.persist import persist_facts
from app.ingestion import ingest_pdf
from app.ingestion.persist import persist_ingestion
from app.providers.factory import get_embedding_provider, get_llm_provider
from app.repository import ProjectScope, create_project, delete_project, list_facts
from app.verification import verify_extraction
from app.verification.persist import persist_verification
from app.verification.schema import VerificationOutcome
from tests._env import db_reachable, provider_available

_IMF = (
    Path(__file__).resolve().parents[3]
    / "datasets"
    / "india-macroeconomy"
    / "03-imf-india-2025-article-iv-excerpt.pdf"
)

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not _IMF.is_file(), reason="datasets/ not available"),
    pytest.mark.skipif(not db_reachable(), reason="no database"),
    pytest.mark.skipif(not provider_available(), reason="no LLM provider"),
]


async def test_imf_article_iv_pages_process_end_to_end() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    llm = get_llm_provider()
    embedder = get_embedding_provider()

    ingestion = ingest_pdf(_IMF.read_bytes(), _IMF.name, render_images=False)
    # the press release + "Executive Board Assessment" pages carry the headline
    # macro facts (GDP growth, inflation, fiscal deficit)
    pages = [3, 4, 5]

    async with maker() as s:
        project = await create_project(s, "unseen-domain-imf")
        pid = project.project_id
        try:
            doc = await persist_ingestion(
                s, pid, ingestion, byte_size=_IMF.stat().st_size, status="extracting"
            )
            await s.commit()

            extraction = await extract_document(
                ingestion, provider=llm, document_id=str(doc.document_id), pages=pages
            )
            assert extraction.stats.llm_calls >= 1
            assert extraction.facts, "expected facts from the IMF assessment pages"

            async with maker() as s2:
                rows = await persist_facts(s2, pid, doc.document_id, extraction)
                fact_ids = [r.fact_id for r in rows]
                await s2.commit()

            verification = await verify_extraction(
                extraction, ingestion.chunks, provider=llm, concurrency=1
            )
            async with maker() as s3:
                await persist_verification(s3, pid, fact_ids, verification)
                await s3.commit()

            async with maker() as s4:
                await compare_document(s4, pid, doc.document_id, llm=llm, embedder=embedder)
                await s4.commit()

            async with maker() as s5:
                scope = ProjectScope(project_id=pid, session=s5)
                facts = list(await list_facts(scope))

            assert facts, "expected persisted facts"
            # domain-agnostic quality checks
            for f in facts:
                assert f.entity and f.attribute and f.evidence_text
                assert f.verification_status in {o.value for o in VerificationOutcome} | {"pending"}
                if f.fact_kind == "quantitative":
                    assert f.value.get("comparator") is not None

            quant = [f for f in facts if f.fact_kind == "quantitative"]
            assert quant, "a macro report should yield quantitative facts"
            # the facts should actually be about the Indian economy, not leak a
            # company-filings assumption
            joined = " ".join(f"{f.entity} {f.attribute}".lower() for f in facts)
            assert any(
                term in joined
                for term in ("gdp", "growth", "inflation", "deficit", "india", "economy", "cpi")
            )
        finally:
            async with maker() as sc:
                await delete_project(sc, pid)
                await sc.commit()

    await llm.aclose()
    await engine.dispose()

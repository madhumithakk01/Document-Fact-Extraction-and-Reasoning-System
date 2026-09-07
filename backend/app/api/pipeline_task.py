"""End-to-end document processing, run in the background after upload.

    queued -> extracting -> verifying -> comparing -> ready   (or -> failed)

Uses its own session and its own provider instances (the request's are gone by
the time this runs).
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from app.comparison.pipeline import compare_document
from app.config import get_settings
from app.db import SessionFactory
from app.extraction import extract_document
from app.extraction.persist import persist_facts
from app.ingestion import ingest_pdf
from app.ingestion.persist import persist_ingestion
from app.models.document import Document
from app.providers.factory import get_embedding_provider, get_llm_provider
from app.verification import verify_extraction
from app.verification.persist import persist_verification

logger = logging.getLogger(__name__)


def stored_pdf_path(content_hash: str) -> Path:
    root = Path(get_settings().upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{content_hash}.pdf"


async def _set_status(document_id: uuid.UUID, status: str, *, error: str | None = None) -> None:
    async with SessionFactory() as session:
        doc = await session.get(Document, document_id)
        if doc is not None:
            doc.processing_status = status
            if error is not None:
                doc.processing_error = error
            await session.commit()


async def process_document(document_id: uuid.UUID, project_id: uuid.UUID) -> None:
    llm = get_llm_provider()
    embedder = get_embedding_provider()
    try:
        async with SessionFactory() as session:
            doc = await session.get(Document, document_id)
            if doc is None:
                logger.warning("process_document: %s no longer exists", document_id)
                return
            data = stored_pdf_path(doc.content_hash).read_bytes()
            filename = doc.filename

        ingestion = ingest_pdf(data, filename, render_images=True)

        async with SessionFactory() as session:
            stored = await persist_ingestion(
                session, project_id, ingestion, byte_size=len(data), status="extracting"
            )
            document_id = stored.document_id
            await session.commit()

        extraction = await extract_document(ingestion, provider=llm, document_id=str(document_id))
        async with SessionFactory() as session:
            fact_rows = await persist_facts(session, project_id, document_id, extraction)
            fact_ids = [r.fact_id for r in fact_rows]
            await session.commit()

        await _set_status(document_id, "verifying")
        verification = await verify_extraction(extraction, ingestion.chunks, provider=llm)
        async with SessionFactory() as session:
            await persist_verification(session, project_id, fact_ids, verification)
            await session.commit()

        await _set_status(document_id, "comparing")
        async with SessionFactory() as session:
            await compare_document(session, project_id, document_id, llm=llm, embedder=embedder)
            await session.commit()

        await _set_status(document_id, "ready")
        logger.info("document %s processed: status=ready", document_id)
    except Exception as exc:  # noqa: BLE001 - record failure, do not crash the worker
        logger.exception("processing failed for document %s", document_id)
        await _set_status(document_id, "failed", error=f"{type(exc).__name__}: {exc}"[:1000])
    finally:
        await llm.aclose()

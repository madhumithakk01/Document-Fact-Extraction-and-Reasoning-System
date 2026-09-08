"""End-to-end document processing, run in the background after upload.

    queued -> extracting -> verifying -> comparing -> ready   (or -> failed)

Uses its own session and its own provider instances (the request's are gone by
the time this runs). The whole pipeline runs under a wall-clock budget scaled to
page count; on timeout or an unrecoverable provider error the document is marked
``failed`` with a message rather than left on ``extracting`` forever.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from app.comparison.pipeline import compare_document
from app.config import get_settings
from app.db import SessionFactory
from app.domain import profile_new_document
from app.extraction import ExtractionProgress, extract_document
from app.extraction.persist import persist_facts
from app.ingestion import ingest_pdf
from app.ingestion.persist import persist_ingestion
from app.ingestion.types import IngestionResult
from app.models.document import Document
from app.providers.base import EmbeddingProvider, LLMProvider
from app.providers.factory import get_embedding_provider, get_llm_provider
from app.providers.observability import RetryNotice, reset_retry_observer, set_retry_observer
from app.verification import verify_extraction
from app.verification.persist import persist_verification

logger = logging.getLogger(__name__)

_MIN_BUDGET_SECONDS = 600.0
_SECONDS_PER_PAGE = 8.0


def stored_pdf_path(content_hash: str) -> Path:
    root = Path(get_settings().upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{content_hash}.pdf"


def _budget_seconds(page_count: int) -> float:
    """Wall-clock ceiling for one document: a floor plus a per-page allowance."""
    return max(_MIN_BUDGET_SECONDS, page_count * _SECONDS_PER_PAGE)


async def _set_status(
    document_id: uuid.UUID,
    status: str,
    *,
    error: str | None = None,
    detail: str | None = None,
) -> None:
    async with SessionFactory() as session:
        doc = await session.get(Document, document_id)
        if doc is not None:
            doc.processing_status = status
            if error is not None:
                doc.processing_error = error
            doc.processing_detail = detail
            await session.commit()


async def process_document(document_id: uuid.UUID, project_id: uuid.UUID) -> None:
    # Both providers are process-wide singletons (see providers.factory). They are
    # shared by every concurrently-processing document and are closed once in the
    # app's lifespan shutdown, never here -- closing the client at the end of one
    # document would break the others mid-flight.
    llm = get_llm_provider()
    embedder = get_embedding_provider()
    budget = _budget_seconds(0)

    # surface provider rate-limit backoff onto this document while it processes
    observer_token = set_retry_observer(lambda notice: _write_retry_detail(document_id, notice))

    try:
        async with SessionFactory() as session:
            doc = await session.get(Document, document_id)
            if doc is None:
                logger.warning("process_document: %s no longer exists", document_id)
                return
            data = stored_pdf_path(doc.content_hash).read_bytes()
            filename = doc.filename

        # page images are rendered lazily by the evidence endpoint, so a large
        # document is not held up rasterising 100 pages nobody may look at
        ingestion = ingest_pdf(data, filename, render_images=False)

        async with SessionFactory() as session:
            stored = await persist_ingestion(
                session, project_id, ingestion, byte_size=len(data), status="extracting"
            )
            document_id = stored.document_id
            stored.pages_total = stored.page_count
            stored.pages_processed = 0
            stored.processing_detail = f"extracting 0/{stored.page_count} pages"
            await session.commit()
            budget = _budget_seconds(stored.page_count)

        await asyncio.wait_for(
            _extract_verify_compare(document_id, project_id, ingestion, llm, embedder),
            timeout=budget,
        )

        await _set_status(document_id, "ready")
        logger.info("document %s processed: status=ready", document_id)
    except TimeoutError:
        minutes = budget / 60
        logger.warning("processing timed out for document %s after ~%.0fm", document_id, minutes)
        await _set_status(
            document_id,
            "failed",
            error=f"processing did not finish within its {minutes:.0f}-minute budget",
            detail="timed out",
        )
    except Exception as exc:  # noqa: BLE001 - record failure, do not crash the worker
        logger.exception("processing failed for document %s", document_id)
        await _set_status(
            document_id, "failed", error=f"{type(exc).__name__}: {exc}"[:1000], detail=None
        )
    finally:
        reset_retry_observer(observer_token)


async def _write_extraction_progress(
    document_id: uuid.UUID, progress: ExtractionProgress
) -> None:
    async with SessionFactory() as session:
        doc = await session.get(Document, document_id)
        if doc is not None:
            doc.pages_processed = progress.pages_done
            doc.processing_detail = (
                f"extracting {progress.pages_done}/{progress.pages_total} pages"
                f" · {progress.facts_so_far} facts so far"
            )
            await session.commit()


async def _write_retry_detail(document_id: uuid.UUID, notice: RetryNotice) -> None:
    async with SessionFactory() as session:
        doc = await session.get(Document, document_id)
        if doc is not None:
            doc.processing_detail = (
                f"rate limited, retrying {notice.attempt}/{notice.max_attempts}"
                f" in {notice.delay_seconds:.0f}s"
            )
            await session.commit()


async def _extract_verify_compare(
    document_id: uuid.UUID,
    project_id: uuid.UUID,
    ingestion: IngestionResult,
    llm: LLMProvider,
    embedder: EmbeddingProvider,
) -> None:
    async def _on_progress(progress: ExtractionProgress) -> None:
        await _write_extraction_progress(document_id, progress)

    extraction = await extract_document(
        ingestion, provider=llm, document_id=str(document_id), on_progress=_on_progress
    )
    async with SessionFactory() as session:
        fact_rows = await persist_facts(session, project_id, document_id, extraction)
        fact_ids = [r.fact_id for r in fact_rows]
        await session.commit()

    await _set_status(document_id, "verifying", detail=f"verifying {len(fact_ids)} facts")
    verification = await verify_extraction(extraction, ingestion.chunks, provider=llm)
    async with SessionFactory() as session:
        await persist_verification(session, project_id, fact_ids, verification)
        await session.commit()

    await _set_status(document_id, "comparing", detail="comparing against existing facts")
    chunk_texts = [c.text for c in ingestion.chunks]
    async with SessionFactory() as session:
        assignment = await profile_new_document(
            session, project_id, document_id, chunk_texts, embedder=embedder
        )
        await session.commit()

    async with SessionFactory() as session:
        await compare_document(
            session,
            project_id,
            document_id,
            llm=llm,
            embedder=embedder,
            off_domain=assignment.off_domain,
        )
        await session.commit()

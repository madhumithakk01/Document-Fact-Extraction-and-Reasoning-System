"""End-to-end document processing, run in the background after upload.

    queued -> extracting -> [partially_ready ->] verifying -> comparing -> ready
    (or -> failed at any point)

Uses its own session and its own provider instances (the request's are gone by
the time this runs). The whole pipeline runs under a wall-clock budget scaled to
page count; on timeout or an unrecoverable provider error the document is marked
``failed`` with a message rather than left on ``extracting`` forever.

A large upload is processed in two passes: the first ~20 pages are extracted and
verified immediately and the document goes to ``partially_ready`` with a visible
fact count, then the remaining pages run in the background. Comparison against
the rest of the project still runs once, over the whole document, at the end.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from sqlalchemy import delete, func, select

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
from app.models.fact import Fact
from app.providers.base import EmbeddingProvider, LLMProvider
from app.providers.factory import get_embedding_provider, get_llm_provider
from app.providers.observability import RetryNotice, reset_retry_observer, set_retry_observer
from app.verification import verify_extraction
from app.verification.persist import persist_verification

logger = logging.getLogger(__name__)

_MIN_BUDGET_SECONDS = 600.0
_SECONDS_PER_PAGE = 8.0

# Large uploads run a fast first pass of this many pages before doing the rest;
# documents at or below the threshold run in a single pass.
_FASTPATH_HEAD_PAGES = 20
_FASTPATH_MIN_TOTAL = 30


def stored_pdf_path(content_hash: str) -> Path:
    root = Path(get_settings().upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{content_hash}.pdf"


def _budget_seconds(page_count: int) -> float:
    """Wall-clock ceiling for one document: a floor plus a per-page allowance."""
    return max(_MIN_BUDGET_SECONDS, page_count * _SECONDS_PER_PAGE)


def _page_phases(all_pages: list[int]) -> list[list[int]]:
    """The pages to process in each pass: one pass for a small document, a fast
    head then the remainder for a large one."""
    if len(all_pages) <= _FASTPATH_MIN_TOTAL:
        return [all_pages]
    return [all_pages[:_FASTPATH_HEAD_PAGES], all_pages[_FASTPATH_HEAD_PAGES:]]


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
            _run_pipeline(document_id, project_id, ingestion, llm, embedder),
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
    document_id: uuid.UUID,
    progress: ExtractionProgress,
    *,
    offset: int,
    grand_total: int,
    label: str,
) -> None:
    done = offset + progress.pages_done
    async with SessionFactory() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            return
        # facts written by any earlier phase, plus the ones this phase has found
        already = await session.scalar(
            select(func.count()).select_from(Fact).where(Fact.document_id == document_id)
        )
        doc.pages_processed = done
        doc.processing_detail = (
            f"{label} {done}/{grand_total} pages"
            f" · {int(already or 0) + progress.facts_so_far} facts so far"
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


async def _run_pipeline(
    document_id: uuid.UUID,
    project_id: uuid.UUID,
    ingestion: IngestionResult,
    llm: LLMProvider,
    embedder: EmbeddingProvider,
) -> None:
    # start from a clean slate so a re-run never doubles up facts a previous
    # attempt already persisted (verification logs and relationships cascade)
    async with SessionFactory() as session:
        await session.execute(delete(Fact).where(Fact.document_id == document_id))
        await session.commit()

    all_pages = sorted({c.page_number for c in ingestion.chunks})
    phases = _page_phases(all_pages)
    grand_total = len(all_pages)
    processed = 0

    for i, phase_pages in enumerate(phases):
        first_of_many = len(phases) > 1 and i == 0
        label = "fast pass · extracting" if first_of_many else "extracting"
        await _extract_and_verify(
            document_id,
            project_id,
            ingestion,
            llm,
            pages=phase_pages,
            offset=processed,
            grand_total=grand_total,
            label=label,
            surface_verifying=(i == len(phases) - 1),
        )
        processed += len(phase_pages)
        if first_of_many:
            async with SessionFactory() as session:
                head_facts = await session.scalar(
                    select(func.count()).select_from(Fact).where(Fact.document_id == document_id)
                )
            await _set_status(
                document_id,
                "partially_ready",
                detail=(
                    f"{processed} of {grand_total} pages ready · {int(head_facts or 0)} facts"
                    f" · processing the rest"
                ),
            )

    await _set_status(document_id, "comparing", detail="comparing against existing facts")
    await _profile_and_compare(document_id, project_id, ingestion, llm, embedder)


async def _extract_and_verify(
    document_id: uuid.UUID,
    project_id: uuid.UUID,
    ingestion: IngestionResult,
    llm: LLMProvider,
    *,
    pages: list[int],
    offset: int,
    grand_total: int,
    label: str,
    surface_verifying: bool,
) -> None:
    async def _on_progress(progress: ExtractionProgress) -> None:
        await _write_extraction_progress(
            document_id, progress, offset=offset, grand_total=grand_total, label=label
        )

    extraction = await extract_document(
        ingestion,
        provider=llm,
        document_id=str(document_id),
        pages=pages,
        on_progress=_on_progress,
    )
    async with SessionFactory() as session:
        fact_rows = await persist_facts(session, project_id, document_id, extraction)
        fact_ids = [r.fact_id for r in fact_rows]
        await session.commit()

    if surface_verifying:
        await _set_status(document_id, "verifying", detail=f"verifying {len(fact_ids)} facts")
    verification = await verify_extraction(extraction, ingestion.chunks, provider=llm)
    async with SessionFactory() as session:
        await persist_verification(session, project_id, fact_ids, verification)
        await session.commit()


async def _profile_and_compare(
    document_id: uuid.UUID,
    project_id: uuid.UUID,
    ingestion: IngestionResult,
    llm: LLMProvider,
    embedder: EmbeddingProvider,
) -> None:
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

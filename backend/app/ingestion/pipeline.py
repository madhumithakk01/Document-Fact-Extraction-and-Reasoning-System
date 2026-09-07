"""Ingestion orchestrator: PDF bytes in, typed anchored chunks out.

    read -> per-page table extraction -> per-page classification -> OCR for
    text-less pages -> page image render -> document profile -> chunking

The result is pure data; persistence is handled separately so the pipeline can
be run from a script or a request handler unchanged.
"""

from __future__ import annotations

import hashlib
import logging

from app.ingestion.chunker import CARRYOVER_TOKENS, build_chunks
from app.ingestion.content_router import build_profile, classify_page
from app.ingestion.ocr import ocr_page
from app.ingestion.page_images import render_and_store
from app.ingestion.pdf_reader import read_pdf
from app.ingestion.types import (
    IngestionResult,
    PageContentType,
    ParsedPage,
)

logger = logging.getLogger(__name__)


def ingest_pdf(
    data: bytes,
    filename: str,
    *,
    render_images: bool = True,
    run_ocr: bool = True,
    carryover_tokens: int = CARRYOVER_TOKENS,
) -> IngestionResult:
    if not data:
        raise ValueError("empty file")

    content_hash = hashlib.sha256(data).hexdigest()
    raw = read_pdf(data)
    pages_with_tables = sum(1 for p in raw.pages if p.tables)
    logger.info(
        "read %s: %d pages, tables on %d pages",
        filename,
        raw.page_count,
        pages_with_tables,
    )

    parsed_pages: list[ParsedPage] = []
    routings = []
    ocr_pages = 0

    for raw_page in raw.pages:
        tables = raw_page.tables
        routing = classify_page(raw_page, tables)
        routings.append(routing)

        text = raw_page.text
        ocr_used = False
        confidence_ceiling = 1.0
        notes = list(routing.notes)

        if routing.content_type == PageContentType.image_only and run_ocr:
            result = ocr_page(data, raw_page.page_number)
            text = result.text or text
            ocr_used = result.used
            confidence_ceiling = result.confidence_ceiling
            notes.append(result.note)
            if result.used:
                ocr_pages += 1

        image_ref = None
        if render_images:
            image_ref = render_and_store(data, content_hash, raw_page.page_number)

        parsed_pages.append(
            ParsedPage(
                page_number=raw_page.page_number,
                content_type=routing.content_type,
                width=raw_page.width,
                height=raw_page.height,
                rotation=raw_page.rotation,
                text=text,
                blocks=raw_page.blocks,
                tables=tables,
                image_ref=image_ref,
                ocr_used=ocr_used,
                confidence_ceiling=confidence_ceiling,
                notes=notes,
            )
        )

    profile = build_profile(raw, routings)
    profile.ocr_pages = ocr_pages

    chunks = build_chunks(parsed_pages, carryover_tokens=carryover_tokens)
    logger.info(
        "%s classified as %s: %d chunks from %d pages",
        filename,
        profile.content_type,
        len(chunks),
        raw.page_count,
    )

    return IngestionResult(
        filename=filename,
        content_hash=content_hash,
        profile=profile,
        pages=parsed_pages,
        chunks=chunks,
    )

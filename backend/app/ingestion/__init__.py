"""Ingestion and content routing.

Turns an uploaded PDF into a set of typed, page-anchored chunks: each page is
classified (text-native, table-heavy, or image/scanned), routed to the matching
extractor, rendered to an image for the evidence panel, and split into a chunk
that carries trailing context from the previous page so cross-page references
resolve downstream.
"""

from app.ingestion.pipeline import ingest_pdf
from app.ingestion.types import (
    Chunk,
    DocumentContentType,
    IngestionResult,
    PageContentType,
    ParsedPage,
    Table,
)

__all__ = [
    "Chunk",
    "DocumentContentType",
    "IngestionResult",
    "PageContentType",
    "ParsedPage",
    "Table",
    "ingest_pdf",
]

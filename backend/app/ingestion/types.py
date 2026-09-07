"""Typed structures passed between ingestion stages.

Nothing in this package hands a bare dict to the next stage. These models are
also what the persistence layer reads when writing ``Document`` and ``Chunk``
rows.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class PageContentType(StrEnum):
    """How a single page's primary content should be treated."""

    text_native = "text_native"
    table_heavy = "table_heavy"
    image_only = "image_only"  # no usable text layer -> OCR path
    empty = "empty"  # blank / section divider, nothing to extract


class DocumentContentType(StrEnum):
    """Document-level routing label, aggregated from page signals."""

    text_native = "text_native"
    scanned = "scanned"
    slides = "slides"
    mixed = "mixed"


class BBox(BaseModel):
    """A rectangle in PDF point coordinates, origin top-left."""

    x0: float
    y0: float
    x1: float
    y1: float

    def union(self, other: BBox) -> BBox:
        return BBox(
            x0=min(self.x0, other.x0),
            y0=min(self.y0, other.y0),
            x1=max(self.x1, other.x1),
            y1=max(self.y1, other.y1),
        )


class TextBlock(BaseModel):
    """A layout block of text with its position, in natural reading order."""

    text: str
    bbox: BBox
    block_index: int


class Table(BaseModel):
    """A structured table, rows and columns preserved (never flattened).

    ``header_rows`` is the count of leading rows that are column headers, so the
    extractor can attach column context to every value it emits.
    """

    rows: list[list[str]]
    header_rows: int = 1
    bbox: BBox

    @property
    def n_cols(self) -> int:
        return max((len(r) for r in self.rows), default=0)

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    def to_markdown(self) -> str:
        if not self.rows:
            return ""
        width = self.n_cols
        norm = [r + [""] * (width - len(r)) for r in self.rows]
        head = norm[0] if self.header_rows else [""] * width
        body = norm[self.header_rows :] if self.header_rows else norm
        lines = [
            "| " + " | ".join(c.replace("\n", " ").strip() for c in head) + " |",
            "| " + " | ".join(["---"] * width) + " |",
        ]
        for r in body:
            lines.append("| " + " | ".join(c.replace("\n", " ").strip() for c in r) + " |")
        return "\n".join(lines)


class ParsedPage(BaseModel):
    """Everything ingestion knows about one page before chunking."""

    page_number: int  # 1-based, as printed order in the file
    content_type: PageContentType
    width: float
    height: float
    rotation: int
    text: str
    blocks: list[TextBlock] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    image_ref: str | None = None  # path to the rendered page image
    ocr_used: bool = False
    confidence_ceiling: float = 1.0  # lowered for OCR / degraded pages
    notes: list[str] = Field(default_factory=list)

    @property
    def has_table(self) -> bool:
        return bool(self.tables)


class Chunk(BaseModel):
    """A page-level unit handed to extraction.

    ``text`` is the page's own content. ``leading_context`` is a trailing slice
    of the previous chunk (~150-200 tokens) so pronouns and split table headers
    resolve; it is provided to the extractor but never re-extracted from.
    """

    page_number: int
    index: int  # 0-based position within the document
    text: str
    leading_context: str = ""
    char_start: int = 0
    char_end: int = 0
    has_table: bool = False
    table_markdown: str | None = None
    image_ref: str | None = None
    content_type: PageContentType = PageContentType.text_native
    confidence_ceiling: float = 1.0

    @property
    def prompt_text(self) -> str:
        """What the extractor sees: carried context, then the page itself."""
        if not self.leading_context:
            return self.text
        return (
            f"[continued from previous page]\n{self.leading_context}\n\n[current page]\n{self.text}"
        )


class DocumentProfile(BaseModel):
    content_type: DocumentContentType
    page_count: int
    pages_text_native: int
    pages_table_heavy: int
    pages_image_only: int
    pages_empty: int
    ocr_pages: int
    producer: str | None = None
    creator: str | None = None
    signals: list[str] = Field(default_factory=list)


class IngestionResult(BaseModel):
    filename: str
    content_hash: str
    profile: DocumentProfile
    pages: list[ParsedPage]
    chunks: list[Chunk]

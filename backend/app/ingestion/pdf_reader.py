"""Low-level PDF reading via PyMuPDF.

Produces a raw, unclassified view of each page: geometry, text in reading order,
layout blocks with bounding boxes, embedded-image coverage, numeric density, and
any structured tables. Classification and routing happen in ``content_router``.

Table finding is by far the most expensive per-page operation, so it is gated by
a cheap structural check and capped by a per-document time budget; pages skipped
because of the budget are still routed correctly from their numeric density and
keep their page image.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

import pymupdf

from app.ingestion.table_extractor import tables_from_page
from app.ingestion.types import BBox, Table, TextBlock

logger = logging.getLogger(__name__)

# A page wider than this (points) is treated as a multi-column spread and its
# blocks are ordered column-first rather than strictly top-to-bottom.
_WIDE_SPREAD_PT = 900.0

# Table-finding gate and budget.
_COLUMN_GAP = re.compile(r"\S(?:\t| {2,})\S")
_MIN_COLUMNAR_LINES = 3
_TABULAR_DIGIT_RATIO = 0.10
_TABLE_TIME_BUDGET_S = 25.0


@dataclass(slots=True)
class RawPage:
    page_number: int
    width: float
    height: float
    rotation: int
    text: str
    blocks: list[TextBlock]
    tables: list[Table]
    char_count: int
    image_count: int
    drawing_count: int
    image_area_ratio: float
    median_font_size: float | None
    digit_ratio: float
    numeric_line_count: int
    table_scan_skipped: bool = False


@dataclass(slots=True)
class RawDocument:
    page_count: int
    producer: str | None
    creator: str | None
    pages: list[RawPage] = field(default_factory=list)


def _order_blocks(raw_blocks: list[tuple], page_width: float) -> list[tuple]:
    """Return text blocks in human reading order.

    PyMuPDF block tuples are ``(x0, y0, x1, y1, text, block_no, block_type)``.
    For wide spreads, sort by column bucket first so the left page/column is
    fully read before the right one.
    """
    text_blocks = [b for b in raw_blocks if b[6] == 0 and b[4].strip()]
    if page_width >= _WIDE_SPREAD_PT:
        mid = page_width / 2

        def key(b: tuple) -> tuple:
            column = 0 if (b[0] + b[2]) / 2 < mid else 1
            return (column, round(b[1], 1), round(b[0], 1))

    else:

        def key(b: tuple) -> tuple:
            return (round(b[1], 1), round(b[0], 1))

    return sorted(text_blocks, key=key)


def _image_area_ratio_and_font(page: pymupdf.Page) -> tuple[float, float | None]:
    """Both signals from one ``rawdict`` pass (rawdict is heavy)."""
    raw = page.get_text("rawdict")
    page_area = abs(page.rect.width * page.rect.height) or 1.0
    covered = 0.0
    sizes: list[float] = []
    for blk in raw.get("blocks", []):
        btype = blk.get("type")
        if btype == 1:  # image block
            x0, y0, x1, y1 = blk["bbox"]
            covered += abs((x1 - x0) * (y1 - y0))
        elif btype == 0:
            for line in blk.get("lines", []):
                for span in line.get("spans", []):
                    sizes.append(float(span["size"]))
    ratio = min(covered / page_area, 1.0)
    median = sorted(sizes)[len(sizes) // 2] if sizes else None
    return ratio, median


def _numeric_stats(text: str) -> tuple[float, int]:
    if not text:
        return 0.0, 0
    digits = sum(c.isdigit() for c in text)
    numeric_lines = sum(
        1
        for line in text.splitlines()
        if line.strip() and sum(c.isdigit() for c in line) / len(line.strip()) > 0.2
    )
    return digits / len(text), numeric_lines


def _maybe_tabular(text: str, digit_ratio: float) -> bool:
    if digit_ratio >= _TABULAR_DIGIT_RATIO:
        return True
    columnar = sum(1 for line in text.splitlines() if _COLUMN_GAP.search(line))
    return columnar >= _MIN_COLUMNAR_LINES


def read_pdf(data: bytes) -> RawDocument:
    doc = pymupdf.open(stream=data, filetype="pdf")
    table_time = 0.0
    try:
        meta = doc.metadata or {}
        out = RawDocument(
            page_count=doc.page_count,
            producer=meta.get("producer") or None,
            creator=meta.get("creator") or None,
        )
        for i, page in enumerate(doc):
            raw_blocks = page.get_text("blocks")
            linear = page.get_text("text")
            ordered = _order_blocks(raw_blocks, page.rect.width)
            blocks = [
                TextBlock(
                    text=b[4].strip(),
                    bbox=BBox(x0=b[0], y0=b[1], x1=b[2], y1=b[3]),
                    block_index=idx,
                )
                for idx, b in enumerate(ordered)
            ]
            text = "\n\n".join(b.text for b in blocks)
            char_count = len(text.strip())
            digit_ratio, numeric_lines = _numeric_stats(linear)
            image_ratio, median_font = _image_area_ratio_and_font(page)
            # get_drawings() is costly on vector-dense pages; only a near-empty
            # page needs it, to tell a blank page from a section divider.
            drawing_count = len(page.get_drawings()) if char_count < 40 else 0

            tables: list[Table] = []
            skipped = False
            if char_count and _maybe_tabular(linear, digit_ratio):
                if table_time < _TABLE_TIME_BUDGET_S:
                    started = time.perf_counter()
                    tables = tables_from_page(page)
                    table_time += time.perf_counter() - started
                else:
                    skipped = True

            out.pages.append(
                RawPage(
                    page_number=i + 1,
                    width=float(page.rect.width),
                    height=float(page.rect.height),
                    rotation=int(page.rotation),
                    text=text,
                    blocks=blocks,
                    tables=tables,
                    char_count=char_count,
                    image_count=len(page.get_images(full=True)),
                    drawing_count=drawing_count,
                    image_area_ratio=image_ratio,
                    median_font_size=median_font,
                    digit_ratio=digit_ratio,
                    numeric_line_count=numeric_lines,
                    table_scan_skipped=skipped,
                )
            )
        if any(p.table_scan_skipped for p in out.pages):
            logger.warning(
                "table scan budget (%.0fs) reached; %d page(s) routed by numeric density only",
                _TABLE_TIME_BUDGET_S,
                sum(1 for p in out.pages if p.table_scan_skipped),
            )
        return out
    finally:
        doc.close()


def render_page_png(data: bytes, page_number: int, dpi: int = 150) -> bytes:
    """Rasterize one page (1-based) to PNG bytes for the evidence panel."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        page = doc[page_number - 1]
        pix = page.get_pixmap(dpi=dpi)
        return pix.tobytes("png")
    finally:
        doc.close()

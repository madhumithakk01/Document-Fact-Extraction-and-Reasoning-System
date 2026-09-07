"""Content-type detection and per-page routing.

Two decisions live here:

* per page -> ``PageContentType`` (text-native / table-heavy / image-only / empty),
  which selects the extractor for that page;
* per document -> ``DocumentContentType`` (text-native / scanned / slides / mixed),
  aggregated from the page signals, surfaced in the UI and used for reporting.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ingestion.pdf_reader import RawDocument, RawPage
from app.ingestion.types import (
    DocumentContentType,
    DocumentProfile,
    PageContentType,
    Table,
)

# --- per-page thresholds ---
_EMPTY_MAX_CHARS = 15
_IMAGE_ONLY_MAX_CHARS = 25
_IMAGE_PRESENT_AREA = 0.15
_IMAGE_RICH_AREA = 0.50
_TABLE_HEAVY_AREA_RATIO = 0.30
_TABLE_HEAVY_MIN_ROWS = 4
_TABLE_HEAVY_MIN_COLS = 3
# Numeric-density fallback: financial statements whose column structure the
# table finder cannot reconstruct (or that were skipped for the time budget)
# are still routed as table-heavy so their page image is kept for the panel.
_TABLE_HEAVY_DIGIT_RATIO = 0.12
_TABLE_HEAVY_NUMERIC_LINES = 6

# --- document thresholds ---
_SCANNED_IMAGE_ONLY_RATIO = 0.60
_MIXED_TEXT_FLOOR = 0.40
_MIXED_IMAGE_RICH_RATIO = 0.10
_MIXED_TABLE_HEAVY_RATIO = 0.15
_SLIDES_MAX_PAGES = 80
_SLIDES_MAX_MEDIAN_CHARS = 1600
_SLIDE_ASPECT_RANGE = (1.25, 1.95)  # 4:3 .. 16:9, landscape


@dataclass(slots=True)
class PageRouting:
    content_type: PageContentType
    image_area_ratio: float
    notes: list[str]


def classify_page(page: RawPage, tables: list[Table]) -> PageRouting:
    notes: list[str] = []
    page_area = abs(page.width * page.height) or 1.0

    if (
        page.char_count < _EMPTY_MAX_CHARS
        and page.image_area_ratio < _IMAGE_PRESENT_AREA
        and page.drawing_count < 5
    ):
        return PageRouting(PageContentType.empty, page.image_area_ratio, ["no extractable content"])

    if page.char_count < _IMAGE_ONLY_MAX_CHARS and (
        page.image_area_ratio >= _IMAGE_PRESENT_AREA or page.image_count >= 1
    ):
        return PageRouting(
            PageContentType.image_only,
            page.image_area_ratio,
            ["no usable text layer; routed to OCR"],
        )

    if tables:
        table_area = sum(abs((t.bbox.x1 - t.bbox.x0) * (t.bbox.y1 - t.bbox.y0)) for t in tables)
        largest = max(tables, key=lambda t: t.n_rows * t.n_cols)
        dominant = (table_area / page_area) >= _TABLE_HEAVY_AREA_RATIO
        substantial = (
            largest.n_rows >= _TABLE_HEAVY_MIN_ROWS and largest.n_cols >= _TABLE_HEAVY_MIN_COLS
        )
        if dominant or substantial:
            notes.append(f"{len(tables)} data table(s); structured parse")
            return PageRouting(PageContentType.table_heavy, page.image_area_ratio, notes)
        notes.append(f"{len(tables)} small table(s) kept alongside prose")

    if (
        page.digit_ratio >= _TABLE_HEAVY_DIGIT_RATIO
        and page.numeric_line_count >= _TABLE_HEAVY_NUMERIC_LINES
    ):
        if page.table_scan_skipped:
            notes.append("high numeric density; structured parse skipped (time budget)")
        elif not tables:
            notes.append("high numeric density; structured parse incomplete on this layout")
        else:
            notes.append("high numeric density with partial table structure")
        return PageRouting(PageContentType.table_heavy, page.image_area_ratio, notes)

    if page.image_area_ratio >= _IMAGE_RICH_AREA:
        notes.append("image-rich page; text layer still present")

    return PageRouting(PageContentType.text_native, page.image_area_ratio, notes)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def _looks_like_slides(raw: RawDocument, routings: list[PageRouting]) -> tuple[bool, str | None]:
    meta = f"{raw.producer or ''} {raw.creator or ''}".lower()
    if "powerpoint" in meta or "keynote" in meta or "impress" in meta or "google slides" in meta:
        return True, "authored in a presentation tool"
    if raw.page_count > _SLIDES_MAX_PAGES:
        return False, None
    landscape = 0
    slide_aspect = 0
    for p in raw.pages:
        if p.width > p.height:
            landscape += 1
            aspect = p.width / max(p.height, 1.0)
            if _SLIDE_ASPECT_RANGE[0] <= aspect <= _SLIDE_ASPECT_RANGE[1]:
                slide_aspect += 1
    median_chars = _median([float(p.char_count) for p in raw.pages])
    if (
        landscape >= raw.page_count * 0.8
        and slide_aspect >= raw.page_count * 0.6
        and median_chars < _SLIDES_MAX_MEDIAN_CHARS
    ):
        return True, "landscape slide-aspect pages with low text density"
    return False, None


def build_profile(raw: RawDocument, routings: list[PageRouting]) -> DocumentProfile:
    n = raw.page_count or 1
    counts = dict.fromkeys(PageContentType, 0)
    for r in routings:
        counts[r.content_type] += 1
    image_rich = sum(1 for r in routings if r.image_area_ratio >= _IMAGE_RICH_AREA)
    signals: list[str] = []

    is_slides, slide_reason = _looks_like_slides(raw, routings)

    text_ratio = counts[PageContentType.text_native] / n
    image_only_ratio = counts[PageContentType.image_only] / n
    table_ratio = counts[PageContentType.table_heavy] / n
    image_rich_ratio = image_rich / n

    if is_slides:
        content_type = DocumentContentType.slides
        if slide_reason:
            signals.append(slide_reason)
    elif image_only_ratio >= _SCANNED_IMAGE_ONLY_RATIO:
        content_type = DocumentContentType.scanned
        signals.append(f"{image_only_ratio:.0%} of pages have no text layer")
    elif text_ratio >= _MIXED_TEXT_FLOOR and (
        image_rich_ratio >= _MIXED_IMAGE_RICH_RATIO
        or table_ratio >= _MIXED_TABLE_HEAVY_RATIO
        or counts[PageContentType.image_only] >= 2
    ):
        content_type = DocumentContentType.mixed
        signals.append(
            f"prose with {table_ratio:.0%} table pages and {image_rich_ratio:.0%} image-rich pages"
        )
    elif table_ratio >= 0.5:
        content_type = DocumentContentType.mixed
        signals.append("table-dominated with supporting prose")
    else:
        content_type = DocumentContentType.text_native
        signals.append("clean font layer throughout")

    if image_rich and content_type != DocumentContentType.slides:
        signals.append(f"{image_rich} image-rich page(s)")

    return DocumentProfile(
        content_type=content_type,
        page_count=raw.page_count,
        pages_text_native=counts[PageContentType.text_native],
        pages_table_heavy=counts[PageContentType.table_heavy],
        pages_image_only=counts[PageContentType.image_only],
        pages_empty=counts[PageContentType.empty],
        ocr_pages=0,  # filled in by the pipeline after OCR actually runs
        producer=raw.producer,
        creator=raw.creator,
        signals=signals,
    )

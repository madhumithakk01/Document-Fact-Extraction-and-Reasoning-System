from __future__ import annotations

from app.ingestion.content_router import build_profile, classify_page
from app.ingestion.pdf_reader import RawDocument, RawPage
from app.ingestion.types import BBox, DocumentContentType, PageContentType, Table


def make_page(
    n: int = 1,
    *,
    text: str = "x" * 2000,
    width: float = 595,
    height: float = 842,
    images: int = 0,
    image_ratio: float = 0.0,
    digit_ratio: float = 0.01,
    numeric_lines: int = 0,
    tables: list[Table] | None = None,
    table_skipped: bool = False,
) -> RawPage:
    return RawPage(
        page_number=n,
        width=width,
        height=height,
        rotation=0,
        text=text,
        blocks=[],
        tables=tables or [],
        char_count=len(text.strip()),
        image_count=images,
        drawing_count=0,
        image_area_ratio=image_ratio,
        median_font_size=11.0,
        digit_ratio=digit_ratio,
        numeric_line_count=numeric_lines,
        table_scan_skipped=table_skipped,
    )


def data_table(rows: int, cols: int, *, bbox: BBox | None = None) -> Table:
    return Table(
        rows=[[f"c{r}{c}" for c in range(cols)] for r in range(rows)],
        header_rows=1,
        bbox=bbox or BBox(x0=50, y0=50, x1=545, y1=750),
    )


def test_blank_page_is_empty() -> None:
    routing = classify_page(make_page(text="  "), [])
    assert routing.content_type is PageContentType.empty


def test_textless_image_page_routes_to_ocr() -> None:
    routing = classify_page(make_page(text="", images=1, image_ratio=0.8), [])
    assert routing.content_type is PageContentType.image_only


def test_large_structured_table_is_table_heavy() -> None:
    t = data_table(rows=8, cols=5)
    routing = classify_page(make_page(digit_ratio=0.05), [t])
    assert routing.content_type is PageContentType.table_heavy


def test_small_table_on_prose_page_stays_text_native() -> None:
    t = data_table(rows=2, cols=2, bbox=BBox(x0=54, y0=60, x1=300, y1=140))
    routing = classify_page(make_page(text="prose " * 400), [t])
    assert routing.content_type is PageContentType.text_native
    assert any("small table" in note for note in routing.notes)


def test_numeric_density_fallback_when_finder_skipped() -> None:
    routing = classify_page(make_page(digit_ratio=0.2, numeric_lines=12, table_skipped=True), [])
    assert routing.content_type is PageContentType.table_heavy
    assert any("time budget" in note for note in routing.notes)


def _doc(pages: list[RawPage], *, creator: str | None = None) -> RawDocument:
    return RawDocument(page_count=len(pages), producer=None, creator=creator, pages=pages)


def test_profile_text_native_document() -> None:
    pages = [make_page(i) for i in range(1, 11)]
    routings = [classify_page(p, p.tables) for p in pages]
    profile = build_profile(_doc(pages), routings)
    assert profile.content_type is DocumentContentType.text_native


def test_profile_detects_slides_from_creator_metadata() -> None:
    pages = [make_page(i, text="headline", width=960, height=540) for i in range(1, 9)]
    routings = [classify_page(p, p.tables) for p in pages]
    profile = build_profile(_doc(pages, creator="Microsoft PowerPoint for Microsoft 365"), routings)
    assert profile.content_type is DocumentContentType.slides


def test_profile_detects_slides_from_geometry() -> None:
    pages = [make_page(i, text="a few words only", width=1024, height=768) for i in range(1, 21)]
    routings = [classify_page(p, p.tables) for p in pages]
    profile = build_profile(_doc(pages), routings)
    assert profile.content_type is DocumentContentType.slides


def test_profile_mixed_when_prose_and_tables_coexist() -> None:
    prose = [make_page(i) for i in range(1, 9)]
    tabley = [
        make_page(i, digit_ratio=0.2, numeric_lines=12, tables=[data_table(8, 5)])
        for i in range(9, 12)
    ]
    pages = prose + tabley
    routings = [classify_page(p, p.tables) for p in pages]
    profile = build_profile(_doc(pages), routings)
    assert profile.content_type is DocumentContentType.mixed


def test_profile_scanned_when_most_pages_have_no_text_layer() -> None:
    pages = [make_page(i, text="", images=1, image_ratio=0.9) for i in range(1, 11)]
    routings = [classify_page(p, p.tables) for p in pages]
    profile = build_profile(_doc(pages), routings)
    assert profile.content_type is DocumentContentType.scanned

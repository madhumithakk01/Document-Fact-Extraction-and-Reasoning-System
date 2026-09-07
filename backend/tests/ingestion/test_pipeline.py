from __future__ import annotations

from app.ingestion import ingest_pdf
from app.ingestion.types import DocumentContentType, PageContentType


def test_prose_pdf_produces_one_anchored_chunk_per_page(prose_pdf: bytes) -> None:
    result = ingest_pdf(prose_pdf, "prose.pdf", render_images=False)
    assert result.profile.content_type is DocumentContentType.text_native
    assert result.profile.page_count == 3
    assert len(result.chunks) == 3
    assert all(c.content_type is PageContentType.text_native for c in result.chunks)
    # anchors are non-overlapping and ordered
    for a, b in zip(result.chunks, result.chunks[1:], strict=False):
        assert b.char_start >= a.char_end
    # context carried onto every page after the first
    assert result.chunks[0].leading_context == ""
    assert all(c.leading_context for c in result.chunks[1:])


def test_content_hash_is_stable(prose_pdf: bytes) -> None:
    a = ingest_pdf(prose_pdf, "prose.pdf", render_images=False)
    b = ingest_pdf(prose_pdf, "prose.pdf", render_images=False)
    assert a.content_hash == b.content_hash


def test_slide_pdf_is_classified_as_slides(slide_pdf: bytes) -> None:
    result = ingest_pdf(slide_pdf, "deck.pdf", render_images=False)
    assert result.profile.content_type is DocumentContentType.slides
    assert len(result.chunks) == 6


def test_blank_page_is_not_chunked(blank_page_pdf: bytes) -> None:
    result = ingest_pdf(blank_page_pdf, "gappy.pdf", render_images=False)
    assert result.profile.page_count == 3
    assert result.profile.pages_empty == 1
    assert [c.page_number for c in result.chunks] == [1, 3]


def test_ocr_skipped_gracefully_when_disabled(blank_page_pdf: bytes) -> None:
    # run_ocr=False must not raise even though there is nothing to OCR here
    result = ingest_pdf(blank_page_pdf, "gappy.pdf", render_images=False, run_ocr=False)
    assert result.profile.ocr_pages == 0


def test_empty_file_rejected() -> None:
    try:
        ingest_pdf(b"", "nothing.pdf")
    except ValueError as exc:
        assert "empty" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for empty input")

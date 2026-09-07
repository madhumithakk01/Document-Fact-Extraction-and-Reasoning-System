from __future__ import annotations

from app.ingestion.chunker import build_chunks
from app.ingestion.types import PageContentType, ParsedPage


def page(n: int, text: str, ctype: PageContentType = PageContentType.text_native) -> ParsedPage:
    return ParsedPage(
        page_number=n,
        content_type=ctype,
        width=595,
        height=842,
        rotation=0,
        text=text,
    )


def test_one_chunk_per_content_page_in_order() -> None:
    pages = [page(1, "First page body."), page(2, "Second page body."), page(3, "Third.")]
    chunks = build_chunks(pages)
    assert [c.page_number for c in chunks] == [1, 2, 3]
    assert [c.index for c in chunks] == [0, 1, 2]


def test_leading_context_carried_from_previous_page() -> None:
    pages = [page(1, "alpha " * 100), page(2, "beta body")]
    chunks = build_chunks(pages, carryover_tokens=20)
    assert chunks[0].leading_context == ""
    assert "alpha" in chunks[1].leading_context
    assert chunks[1].prompt_text.startswith("[continued from previous page]")


def test_blank_page_is_skipped_but_offsets_stay_aligned() -> None:
    pages = [page(1, "one one one"), page(2, "", PageContentType.empty), page(3, "three three")]
    chunks = build_chunks(pages)
    assert [c.page_number for c in chunks] == [1, 3]
    assert chunks[1].char_start >= chunks[0].char_end


def test_image_only_page_kept_even_without_text() -> None:
    pages = [page(1, "intro text"), page(2, "", PageContentType.image_only), page(3, "outro")]
    chunks = build_chunks(pages)
    assert [c.page_number for c in chunks] == [1, 2, 3]
    assert chunks[1].text == ""
    # context still flows across the textless page
    assert "intro" in chunks[2].leading_context


def test_char_offsets_are_monotonic() -> None:
    pages = [page(i, f"page {i} " * 20) for i in range(1, 6)]
    chunks = build_chunks(pages)
    for earlier, later in zip(chunks, chunks[1:], strict=False):
        assert later.char_start >= earlier.char_end

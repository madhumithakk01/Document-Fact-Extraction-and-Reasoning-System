"""End-to-end checks against the real source PDFs.

These files live outside the repository. When the ``datasets`` directory is not
present (CI, a fresh clone) the module is skipped.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ingestion import ingest_pdf
from app.ingestion.types import DocumentContentType

_DATASETS = Path(__file__).resolve().parents[3] / "datasets"
_PDFS = sorted(_DATASETS.rglob("*.pdf")) if _DATASETS.is_dir() else []

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not _PDFS, reason="datasets/ not available"),
]


@pytest.mark.parametrize("pdf_path", _PDFS, ids=lambda p: p.name)
def test_real_pdf_ingests_to_typed_anchored_chunks(pdf_path: Path) -> None:
    result = ingest_pdf(pdf_path.read_bytes(), pdf_path.name, render_images=False)

    assert result.profile.page_count > 0
    assert result.profile.content_type in set(DocumentContentType)
    assert result.chunks, "expected at least one chunk"

    # every chunk is anchored to a real page and ordered
    pages = {c.page_number for c in result.chunks}
    assert min(pages) >= 1
    assert max(pages) <= result.profile.page_count
    for a, b in zip(result.chunks, result.chunks[1:], strict=False):
        assert b.index == a.index + 1
        assert b.char_start >= a.char_end

    # context carryover reaches almost every non-first chunk
    carried = sum(1 for c in result.chunks[1:] if c.leading_context)
    assert carried >= len(result.chunks) - 2

    # page routing counts reconcile with the page total
    p = result.profile
    assert (
        p.pages_text_native + p.pages_table_heavy + p.pages_image_only + p.pages_empty
        == p.page_count
    )


def test_earnings_deck_detected_as_slides() -> None:
    deck = next((p for p in _PDFS if "earnings" in p.name.lower()), None)
    if deck is None:
        pytest.skip("earnings deck not in datasets/")
    result = ingest_pdf(deck.read_bytes(), deck.name, render_images=False)
    assert result.profile.content_type is DocumentContentType.slides

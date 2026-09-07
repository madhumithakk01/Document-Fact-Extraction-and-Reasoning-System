"""Performance / robustness pass: every real source PDF ingests to typed,
anchored chunks within a time budget, with no domain-specific breakage."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.ingestion import ingest_pdf
from app.ingestion.types import DocumentContentType, PageContentType

_DATASETS = Path(__file__).resolve().parents[3] / "datasets"
_PDFS = sorted(_DATASETS.rglob("*.pdf")) if _DATASETS.is_dir() else []

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not _PDFS, reason="datasets/ not available"),
]

# generous ceiling; the slowest (100-page landscape InDesign report) is ~35s
_MAX_SECONDS_PER_DOC = 90.0


@pytest.mark.parametrize("pdf_path", _PDFS, ids=lambda p: p.name)
def test_ingests_within_budget_and_produces_valid_chunks(pdf_path: Path) -> None:
    data = pdf_path.read_bytes()

    started = time.perf_counter()
    result = ingest_pdf(data, pdf_path.name, render_images=False)
    elapsed = time.perf_counter() - started

    assert elapsed < _MAX_SECONDS_PER_DOC, f"{pdf_path.name} took {elapsed:.1f}s"
    assert result.profile.content_type in set(DocumentContentType)
    assert result.profile.page_count > 0

    # every chunk is anchored to a real page, in order, with monotonic offsets
    assert result.chunks
    for a, b in zip(result.chunks, result.chunks[1:], strict=False):
        assert b.index == a.index + 1
        assert b.char_start >= a.char_end
    for c in result.chunks:
        assert 1 <= c.page_number <= result.profile.page_count
        assert c.content_type in set(PageContentType)

    counts = result.profile
    assert (
        counts.pages_text_native
        + counts.pages_table_heavy
        + counts.pages_image_only
        + counts.pages_empty
        == counts.page_count
    )


def test_macro_economic_documents_route_sensibly() -> None:
    """The macro-economic reports were never tuned against; routing must still
    make sense (prose-first, tables detected, image-only cover handled)."""
    macro = [p for p in _PDFS if "macroeconomy" in str(p)]
    assert macro, "expected the india-macroeconomy dataset"

    for pdf_path in macro:
        result = ingest_pdf(pdf_path.read_bytes(), pdf_path.name, render_images=False)
        p = result.profile
        # these are prose-heavy institutional reports
        assert p.pages_text_native >= p.page_count * 0.4
        # every one has at least some statistical tables
        assert p.pages_table_heavy >= 1
        # nothing crashed on the chart-heavy / cover pages
        assert result.chunks

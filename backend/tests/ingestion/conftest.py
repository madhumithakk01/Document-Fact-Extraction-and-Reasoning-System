"""Synthetic PDF builders so ingestion tests do not depend on any external file."""

from __future__ import annotations

import pymupdf
import pytest


def _text_page(doc: pymupdf.Document, lines: list[str], size: tuple[float, float]) -> None:
    page = doc.new_page(width=size[0], height=size[1])
    y = 60.0
    for line in lines:
        page.insert_text((54, y), line, fontsize=11)
        y += 16


@pytest.fixture
def prose_pdf() -> bytes:
    """Three portrait pages of running prose."""
    doc = pymupdf.open()
    _text_page(
        doc,
        [
            "Introduction to the Acme Corporation annual filing.",
            "The company reported revenue of 1,234 crore for the year.",
            "It operates across seventeen states and two union territories.",
        ]
        + [f"Filler sentence number {i} providing body text." for i in range(12)],
        (595, 842),
    )
    _text_page(
        doc,
        [
            "As noted above, the group continued its expansion.",
            "EBITDA margin improved to 6.5 percent in the period.",
        ]
        + [f"Second page filler line {i} with more detail." for i in range(14)],
        (595, 842),
    )
    _text_page(
        doc,
        [f"Third page paragraph {i} closing out the section." for i in range(16)],
        (595, 842),
    )
    return doc.tobytes()


@pytest.fixture
def slide_pdf() -> bytes:
    """Landscape 16:9 pages with sparse text, as a deck exports."""
    doc = pymupdf.open()
    for n in range(6):
        _text_page(doc, [f"Slide {n + 1} headline", "One supporting bullet."], (960, 540))
    return doc.tobytes()


@pytest.fixture
def blank_page_pdf() -> bytes:
    """Two prose pages around one genuinely empty page."""
    doc = pymupdf.open()
    _text_page(doc, [f"Alpha page line {i}." for i in range(14)], (595, 842))
    doc.new_page(width=595, height=842)  # blank
    _text_page(doc, [f"Gamma page line {i}." for i in range(14)], (595, 842))
    return doc.tobytes()

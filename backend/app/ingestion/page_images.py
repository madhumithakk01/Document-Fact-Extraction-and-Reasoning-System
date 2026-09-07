"""Persist rendered page images for the evidence panel.

Images are written under ``PAGE_IMAGE_DIR/<content_hash>/<page>.png``. The
returned reference is the path relative to that root, which is what a ``Chunk``
and later a ``Fact`` store.
"""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.ingestion.pdf_reader import render_page_png


def page_image_root() -> Path:
    root = Path(get_settings().page_image_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def render_and_store(data: bytes, content_hash: str, page_number: int, dpi: int = 150) -> str:
    doc_dir = page_image_root() / content_hash
    doc_dir.mkdir(parents=True, exist_ok=True)
    target = doc_dir / f"{page_number}.png"
    if not target.exists():
        target.write_bytes(render_page_png(data, page_number, dpi=dpi))
    return str(target.relative_to(page_image_root()).as_posix())

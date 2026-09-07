"""OCR fallback for pages with no usable text layer.

Only invoked when content routing marks a page ``image_only``. If Tesseract is
not installed the page is not dropped: it is returned with empty text, a note,
and a lowered confidence ceiling so downstream stages can treat it accordingly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.ingestion.pdf_reader import render_page_png

logger = logging.getLogger(__name__)

# Facts drawn from OCR text cannot be trusted as highly as facts from a clean
# font layer; extraction and verification read this ceiling.
OCR_CONFIDENCE_CEILING = 0.6


@dataclass(slots=True)
class OcrResult:
    text: str
    used: bool
    confidence_ceiling: float
    note: str


def _tesseract_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001 - any failure means "not usable"
        return False


def ocr_page(data: bytes, page_number: int, dpi: int = 300) -> OcrResult:
    if not _tesseract_available():
        logger.warning(
            "page %d has no text layer and Tesseract is unavailable; "
            "keeping the page with empty text",
            page_number,
        )
        return OcrResult(
            text="",
            used=False,
            confidence_ceiling=OCR_CONFIDENCE_CEILING,
            note="no text layer; OCR unavailable (Tesseract not installed)",
        )

    import io

    import pytesseract
    from PIL import Image

    png = render_page_png(data, page_number, dpi=dpi)
    image = Image.open(io.BytesIO(png))
    text = pytesseract.image_to_string(image).strip()
    return OcrResult(
        text=text,
        used=True,
        confidence_ceiling=OCR_CONFIDENCE_CEILING,
        note="text recovered via OCR" if text else "OCR produced no text",
    )

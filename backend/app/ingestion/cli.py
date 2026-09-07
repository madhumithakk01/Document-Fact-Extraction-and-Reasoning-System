"""Run ingestion on a PDF from the command line and print the routing report.

python -m app.ingestion.cli path/to/file.pdf
python -m app.ingestion.cli path/to/file.pdf --json
python -m app.ingestion.cli path/to/file.pdf --no-images --no-ocr
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.ingestion.pipeline import ingest_pdf
from app.ingestion.types import IngestionResult
from app.logging_config import configure_logging

# Source PDFs carry rupee signs, en dashes, and other non-ASCII; make the
# report printable on a legacy Windows console too.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _summary(result: IngestionResult) -> str:
    p = result.profile
    lines = [
        f"file            {result.filename}",
        f"content hash    {result.content_hash[:16]}...",
        f"document type   {p.content_type}",
        f"pages           {p.page_count}",
        f"  text-native   {p.pages_text_native}",
        f"  table-heavy   {p.pages_table_heavy}",
        f"  image-only    {p.pages_image_only}",
        f"  empty         {p.pages_empty}",
        f"  OCR applied   {p.ocr_pages}",
        f"creator         {p.creator or '-'}",
        f"signals         {'; '.join(p.signals) or '-'}",
        f"chunks          {len(result.chunks)}",
    ]
    tabled = [c for c in result.chunks if c.has_table]
    carried = [c for c in result.chunks if c.leading_context]
    lines.append(f"  with tables   {len(tabled)}")
    lines.append(f"  with context  {len(carried)}")
    lines.append("")
    lines.append("first chunks:")
    for c in result.chunks[:5]:
        preview = " ".join(c.text.split())[:90]
        lines.append(
            f"  p{c.page_number:<4} idx {c.index:<3} {c.content_type:<12} "
            f"ctx={len(c.leading_context):>4}c  {preview}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.ingestion.cli")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--json", action="store_true", help="emit the full result as JSON")
    parser.add_argument("--no-images", action="store_true", help="skip page image rendering")
    parser.add_argument("--no-ocr", action="store_true", help="skip the OCR fallback")
    args = parser.parse_args(argv)

    configure_logging("INFO")
    if not args.pdf.is_file():
        print(f"no such file: {args.pdf}", file=sys.stderr)
        return 2

    result = ingest_pdf(
        args.pdf.read_bytes(),
        args.pdf.name,
        render_images=not args.no_images,
        run_ocr=not args.no_ocr,
    )

    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        print(_summary(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

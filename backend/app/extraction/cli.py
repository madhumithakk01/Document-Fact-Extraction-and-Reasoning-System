"""Ingest a PDF and run fact extraction over it, then print the facts.

    python -m app.extraction.cli file.pdf --pages 6,22
    python -m app.extraction.cli file.pdf --max-chunks 5 --json

Needs a configured provider: set GROQ_API_KEY in .env, or run Ollama locally and
set LLM_PROVIDER=ollama.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.extraction.extractor import extract_document
from app.extraction.schema import ExtractionResult
from app.ingestion import ingest_pdf
from app.logging_config import configure_logging
from app.providers.base import ProviderError
from app.providers.factory import get_llm_provider

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _format_value(af) -> str:  # type: ignore[no-untyped-def]
    v = af.candidate.value
    if af.candidate.fact_kind.value == "quantitative":
        cmp = v.comparator.value if v.comparator else "?"
        num = "" if v.number is None else f"{v.number:g}"
        if v.comparator and v.comparator.value == "range":
            num = f"{v.number:g}-{v.number_high:g}" if v.number_high is not None else num
        return f"{cmp} {num} {v.unit or ''}".strip()
    if af.candidate.fact_kind.value == "status":
        return v.state or ""
    return (v.text or "")[:60]


def _summary(result: ExtractionResult) -> str:
    s = result.stats
    lines = [
        f"file             {result.document_filename}",
        f"chunks called    {s.chunks_called}/{s.chunks_seen}   failed {s.chunks_failed}",
        f"llm calls        {s.llm_calls}",
        f"facts returned   {s.facts_returned}",
        f"facts kept       {s.facts_kept}   by kind {s.by_kind}",
        f"unanchored       {s.unanchored}",
        f"dropped          invalid {s.dropped_invalid}, no-column {s.dropped_no_column_context}",
        f"comparator fixes {s.comparator_repaired}",
        "",
    ]
    for af in result.facts[:40]:
        p = af.anchor.page_number if af.anchor else "?"
        flag = "" if af.anchored else "  [UNANCHORED]"
        period = af.candidate.period.raw_label or "-"
        lines.append(
            f"  p{p!s:<4} {af.candidate.fact_kind.value:<12} "
            f"{af.candidate.entity[:28]:<28} | {af.candidate.attribute[:28]:<28} | "
            f"{_format_value(af)[:24]:<24} | {period[:10]:<10} "
            f"c={af.candidate.extraction_confidence:.2f}{flag}"
        )
    if len(result.facts) > 40:
        lines.append(f"  ... and {len(result.facts) - 40} more")
    return "\n".join(lines)


def _parse_pages(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


async def _run(args: argparse.Namespace) -> int:
    try:
        provider = get_llm_provider()
    except ProviderError as exc:
        print(f"no usable LLM provider: {exc}", file=sys.stderr)
        print(
            "set GROQ_API_KEY in backend/.env, or LLM_PROVIDER=ollama with Ollama running.",
            file=sys.stderr,
        )
        return 3

    data = args.pdf.read_bytes()
    ingestion = ingest_pdf(data, args.pdf.name, render_images=False)
    result = await extract_document(
        ingestion,
        provider=provider,
        concurrency=args.concurrency,
        max_chunks=args.max_chunks,
        pages=_parse_pages(args.pages),
    )
    await provider.aclose()

    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        print(_summary(result))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.extraction.cli")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--pages", help="comma list / ranges, e.g. 6,22-24")
    parser.add_argument("--max-chunks", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    configure_logging("INFO")
    if not args.pdf.is_file():
        print(f"no such file: {args.pdf}", file=sys.stderr)
        return 2
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())

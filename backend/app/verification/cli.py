"""Ingest, extract, and verify a PDF, then print the facts with their status.

    python -m app.verification.cli file.pdf --pages 5,6
    python -m app.verification.cli file.pdf --max-chunks 4 --json

Needs a configured provider (GROQ_API_KEY in .env, or LLM_PROVIDER=ollama).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.extraction.cli import _parse_pages
from app.extraction.extractor import extract_document
from app.ingestion import ingest_pdf
from app.logging_config import configure_logging
from app.providers.base import ProviderError
from app.providers.factory import get_llm_provider
from app.verification import verify_extraction
from app.verification.schema import VerificationResult

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_BADGE = {
    "verified": "OK  ",
    "auto_corrected": "FIX ",
    "needs_review": "??  ",
    "rejected": "REJ ",
}


def _summary(result: VerificationResult) -> str:
    s = result.stats
    lines = [
        f"file             {result.document_filename}",
        f"facts in         {s.facts_in}",
        f"  verified       {s.verified}",
        f"  auto-corrected {s.auto_corrected}",
        f"  needs review   {s.needs_review}",
        f"  rejected       {s.rejected}  (grounding failures {s.grounding_failures})",
        f"verifier calls   {s.verifier_calls}   errors {s.verifier_errors}   "
        f"corrections {s.correction_attempts}",
        "",
    ]
    for fv in result.verifications[:50]:
        f = fv.effective_fact
        page = fv.fact.anchor.page_number if fv.fact.anchor else "?"
        vc = "" if fv.verifier_confidence is None else f" v={fv.verifier_confidence:.2f}"
        note = f"  <- {fv.notes[0]}" if fv.notes else ""
        lines.append(
            f"  {_BADGE.get(fv.final_status.value, '    ')} p{page!s:<3} "
            f"{f.entity[:24]:<24} | {f.attribute[:26]:<26} | "
            f"{(f.value.text or f.value.state or str(f.value.number))[:20]:<20}"
            f"{vc}{note}"
        )
    return "\n".join(lines)


async def _run(args: argparse.Namespace) -> int:
    try:
        provider = get_llm_provider()
    except ProviderError as exc:
        print(f"no usable LLM provider: {exc}", file=sys.stderr)
        return 3

    ingestion = ingest_pdf(args.pdf.read_bytes(), args.pdf.name, render_images=False)
    extraction = await extract_document(
        ingestion,
        provider=provider,
        concurrency=args.concurrency,
        max_chunks=args.max_chunks,
        pages=_parse_pages(args.pages),
    )
    verification = await verify_extraction(
        extraction, ingestion.chunks, provider=provider, concurrency=args.concurrency
    )
    await provider.aclose()

    if args.json:
        print(verification.model_dump_json(indent=2))
    else:
        print(_summary(verification))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.verification.cli")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--pages", help="comma list / ranges, e.g. 5,6-8")
    parser.add_argument("--max-chunks", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    configure_logging("INFO")
    if not args.pdf.is_file():
        print(f"no such file: {args.pdf}", file=sys.stderr)
        return 2
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())

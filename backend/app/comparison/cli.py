"""Run the deterministic pre-check over a document's verified facts.

    python -m app.comparison.cli file.pdf --pages 5,6

Extraction and verification use the provider; the pairwise comparison itself
makes zero model calls. Prints every pair the pre-check resolves as
corroborating, and a count of the pairs it hands to adjudication.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import sys
from pathlib import Path

from app.comparison.precheck import ComparableFact, PrecheckOutcome, deterministic_precheck
from app.extraction.cli import _parse_pages
from app.extraction.extractor import extract_document
from app.ingestion import ingest_pdf
from app.logging_config import configure_logging
from app.providers.base import ProviderError
from app.providers.factory import get_llm_provider
from app.verification import verify_extraction
from app.verification.schema import VerificationOutcome

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _label(cf: ComparableFact) -> str:
    v = cf.value
    val = (
        v.get("text")
        or v.get("state")
        or (f"{v.get('comparator', '')} {v.get('number', '')} {v.get('unit', '') or ''}".strip())
    )
    return f"{cf.entity[:22]} / {cf.attribute[:24]} = {val} [{cf.period.get('raw_label') or '-'}]"


async def _run(args: argparse.Namespace) -> int:
    try:
        provider = get_llm_provider()
    except ProviderError as exc:
        print(f"no usable LLM provider: {exc}", file=sys.stderr)
        return 3

    ingestion = ingest_pdf(args.pdf.read_bytes(), args.pdf.name, render_images=False)
    extraction = await extract_document(
        ingestion, provider=provider, pages=_parse_pages(args.pages), max_chunks=args.max_chunks
    )
    verification = await verify_extraction(extraction, ingestion.chunks, provider=provider)
    await provider.aclose()

    usable = [
        ComparableFact(
            fact_kind=fv.effective_fact.fact_kind.value,
            entity=fv.effective_fact.entity,
            attribute=fv.effective_fact.attribute,
            value=fv.effective_fact.value.model_dump(exclude_none=True),
            period=fv.effective_fact.period.model_dump(exclude_none=True),
            qualifiers=fv.effective_fact.qualifiers,
        )
        for fv in verification.verifications
        if fv.final_status in (VerificationOutcome.verified, VerificationOutcome.auto_corrected)
    ]

    print(
        f"{len(usable)} usable fact(s); running {len(usable) * (len(usable) - 1) // 2} pairs "
        f"through the deterministic pre-check (0 model calls)\n"
    )

    counts = dict.fromkeys(PrecheckOutcome, 0)
    for a, b in itertools.combinations(usable, 2):
        result = deterministic_precheck(a, b)
        counts[result.outcome] += 1
        if result.outcome is PrecheckOutcome.corroborates:
            print(f"  CORROBORATES  {_label(a)}")
            print(f"           <->  {_label(b)}")
            print(f"                {result.reason}\n")

    print(
        f"summary: {counts[PrecheckOutcome.corroborates]} corroborated, "
        f"{counts[PrecheckOutcome.needs_adjudication]} need adjudication, "
        f"{counts[PrecheckOutcome.not_comparable]} not comparable"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.comparison.cli")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--pages", help="comma list / ranges")
    parser.add_argument("--max-chunks", type=int, default=None)
    args = parser.parse_args(argv)

    configure_logging("INFO")
    if not args.pdf.is_file():
        print(f"no such file: {args.pdf}", file=sys.stderr)
        return 2
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())

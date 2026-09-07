"""Verify every fact from an extraction run."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from app.extraction.schema import ExtractionResult
from app.ingestion.types import Chunk
from app.providers import get_llm_provider
from app.providers.base import LLMProvider
from app.verification.schema import (
    FactVerification,
    VerificationOutcome,
    VerificationResult,
    VerificationStats,
)
from app.verification.verifier import verify_fact

logger = logging.getLogger(__name__)


async def verify_extraction(
    extraction: ExtractionResult,
    chunks: Sequence[Chunk],
    *,
    provider: LLMProvider | None = None,
    concurrency: int = 3,
) -> VerificationResult:
    provider = provider or get_llm_provider()
    chunk_by_index = {c.index: c for c in chunks}
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _run(af) -> FactVerification:  # type: ignore[no-untyped-def]
        chunk = chunk_by_index.get(af.anchor.chunk_index) if af.anchor is not None else None
        async with semaphore:
            return await verify_fact(af, chunk, provider)

    verifications = await asyncio.gather(*(_run(af) for af in extraction.facts))

    stats = VerificationStats(facts_in=len(verifications))
    for fv in verifications:
        stats.record(fv.final_status)
        if fv.final_status is VerificationOutcome.rejected:
            stats.grounding_failures += 1
        if any(e.detail.get("correction") for e in fv.log):
            stats.correction_attempts += 1
        for entry in fv.log:
            if entry.stage.value != "independent_verify":
                continue
            if entry.result == "error":
                stats.verifier_errors += 1
            else:
                stats.verifier_calls += 1

    logger.info(
        "verified %s: %d verified, %d auto-corrected, %d needs-review, %d rejected (of %d)",
        extraction.document_filename,
        stats.verified,
        stats.auto_corrected,
        stats.needs_review,
        stats.rejected,
        stats.facts_in,
    )
    return VerificationResult(
        document_filename=extraction.document_filename,
        content_hash=extraction.content_hash,
        verifications=list(verifications),
        stats=stats,
    )

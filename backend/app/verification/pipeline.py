"""Verify every fact from an extraction run."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from app.config import DualExtractMode, Settings, get_settings
from app.extraction.schema import ExtractionResult
from app.ingestion.types import Chunk
from app.providers import get_llm_provider
from app.providers.base import LLMProvider, ProviderError
from app.providers.factory import build_single_provider
from app.verification.dual_extract import blind_reextract, independent_corroborate
from app.verification.schema import (
    FactVerification,
    VerificationLogEntry,
    VerificationOutcome,
    VerificationResult,
    VerificationStage,
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

    settings = get_settings()
    if settings.dual_extract_mode is not DualExtractMode.off:
        await _apply_dual_extraction(list(verifications), chunk_by_index, settings)

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


def _fact_confidence(fv: FactVerification) -> float:
    if fv.verifier_confidence is not None:
        return fv.verifier_confidence
    return fv.effective_fact.extraction_confidence


def _matches(fv: FactVerification, terms: list[str]) -> bool:
    if not terms:
        return False
    hay = f"{fv.effective_fact.entity} {fv.effective_fact.attribute}".lower()
    return any(t.lower() in hay for t in terms)


def _select_for_dual_extraction(
    verifications: list[FactVerification], settings: Settings
) -> list[FactVerification]:
    anchored = [fv for fv in verifications if fv.fact.anchor is not None]
    if settings.dual_extract_mode is DualExtractMode.all:
        return anchored

    matched = [fv for fv in anchored if _matches(fv, settings.dual_extract_match)]
    matched_ids = {id(fv) for fv in matched}
    rest = sorted(
        (fv for fv in anchored if id(fv) not in matched_ids), key=_fact_confidence
    )
    return matched + rest[: max(0, settings.dual_extract_limit - len(matched))]


async def _apply_dual_extraction(
    verifications: list[FactVerification],
    chunk_by_index: dict[int, Chunk],
    settings: Settings,
) -> None:
    if settings.dual_extract_provider is settings.llm_provider:
        logger.warning(
            "dual_extract_provider (%s) is the primary provider; skipping - a second "
            "extraction from the same model is not independent",
            settings.dual_extract_provider.value,
        )
        return

    selected = _select_for_dual_extraction(verifications, settings)
    if not selected:
        return

    try:
        blind_provider = build_single_provider(
            settings,
            settings.dual_extract_provider,
            timeout_seconds=settings.dual_extract_timeout_seconds,
        )
    except ProviderError as exc:
        logger.warning("dual extraction unavailable: %s", exc)
        return

    blind_name = blind_provider.name
    blind_by_chunk: dict[int, list] = {}
    try:
        for chunk_index in {fv.fact.anchor.chunk_index for fv in selected}:
            chunk = chunk_by_index.get(chunk_index)
            if chunk is None:
                continue
            try:
                blind_by_chunk[chunk_index] = await blind_reextract(chunk, blind_provider)
            except ProviderError as exc:
                logger.warning("blind re-extraction failed on chunk %d: %s", chunk_index, exc)
    finally:
        await blind_provider.aclose()

    for fv in selected:
        blind = blind_by_chunk.get(fv.fact.anchor.chunk_index)
        if blind is None:
            continue
        result = independent_corroborate(
            fv.effective_fact,
            [b.candidate for b in blind],
            blind_provider=blind_name,
        )
        fv.corroboration = result.as_dict()
        fv.verifier_confidence = result.confidence  # replaces the flat verifier value
        fv.log = [
            *fv.log,
            VerificationLogEntry(
                stage=VerificationStage.dual_extraction,
                result=result.status,
                issue=None,
                detail=result.as_dict(),
            ),
        ]
        if result.needs_human_review and fv.final_status in (
            VerificationOutcome.verified,
            VerificationOutcome.auto_corrected,
        ):
            fv.final_status = VerificationOutcome.needs_review
            fv.notes = [*fv.notes, "no independent extraction corroborated this fact"]

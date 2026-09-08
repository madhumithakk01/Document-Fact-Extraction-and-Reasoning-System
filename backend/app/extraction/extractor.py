"""Run the schema-constrained extraction call over a document's chunks.

Per chunk: one model call, validate each returned fact, apply the deterministic
comparator safety net, enforce table column context, anchor the evidence span,
cap confidence at the chunk's ceiling. Output is unverified ``AnchoredFact``s.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from app.extraction.anchoring import anchor_evidence
from app.extraction.prompts import SYSTEM_PROMPT, build_user_prompt
from app.extraction.schema import (
    EXTRACTION_JSON_SCHEMA,
    AnchoredFact,
    CandidateFact,
    Comparator,
    ExtractionResult,
    ExtractionStats,
    FactKind,
)
from app.ingestion.types import Chunk, IngestionResult
from app.providers import get_llm_provider
from app.providers.base import CompletionRequest, LLMProvider, ProviderError

logger = logging.getLogger(__name__)

_MIN_CHUNK_CHARS = 40
_COLUMN_QUALIFIER_KEYS = ("column_header", "column", "col_header", "col")

_JSON_FALLBACK_INSTRUCTION = (
    '\n\nReturn ONLY a JSON object of the form {"facts": [ ... ]}. Each fact has '
    "fact_kind, entity, entity_resolved, attribute, value (object with comparator, "
    "number, number_high, unit, state, text), period (object with raw_label, "
    "start_date, end_date), qualifiers (list of {name, value}), evidence_text, and "
    "extraction_confidence. No prose, no markdown fences."
)


def _is_schema_rejection(exc: ProviderError) -> bool:
    msg = str(exc).lower()
    return any(
        s in msg
        for s in (
            "response_format",
            "json schema",
            "json_schema",
            "does not match the expected schema",
            "generated json",
        )
    )


# Approximate-language -> comparator, longest phrases first so "at least" wins
# over "least" etc. Applied only when the model left the comparator as eq/None.
_APPROX_PATTERNS: list[tuple[re.Pattern[str], Comparator]] = [
    (re.compile(r"\bno more than\b", re.I), Comparator.lte),
    (re.compile(r"\bup to\b", re.I), Comparator.lte),
    (re.compile(r"\bat least\b", re.I), Comparator.gte),
    (re.compile(r"\bat most\b", re.I), Comparator.lte),
    (re.compile(r"\bmore than\b", re.I), Comparator.gt),
    (re.compile(r"\bgreater than\b", re.I), Comparator.gt),
    (re.compile(r"\bless than\b", re.I), Comparator.lt),
    (re.compile(r"\bfewer than\b", re.I), Comparator.lt),
    (re.compile(r"\bover\b", re.I), Comparator.gt),
    (re.compile(r"\bunder\b", re.I), Comparator.lt),
    (re.compile(r"\bexceed(?:s|ed|ing)?\b", re.I), Comparator.gt),
    (
        re.compile(r"\b(?:approximately|approx\.?|about|around|roughly|nearly|circa)\b", re.I),
        Comparator.approx,
    ),
    (re.compile(r"~\s*\d"), Comparator.approx),
]


def repair_comparator(fact: CandidateFact) -> bool:
    """Deterministic backstop for §6.2: approximated language must never read as
    exact equality. Returns True if the comparator was changed."""
    if fact.fact_kind is not FactKind.quantitative:
        return False
    current = fact.value.comparator
    if current not in (None, Comparator.eq):
        return False
    for pattern, comparator in _APPROX_PATTERNS:
        if pattern.search(fact.evidence_text):
            fact.value.comparator = comparator
            return True
    if current is None:
        fact.value.comparator = Comparator.eq
    return False


def _has_column_context(fact: CandidateFact) -> bool:
    keys = {k.lower() for k in fact.qualifiers}
    return any(k in keys for k in _COLUMN_QUALIFIER_KEYS)


def _parse_facts(payload: object) -> list[dict]:
    if isinstance(payload, dict) and isinstance(payload.get("facts"), list):
        return [f for f in payload["facts"] if isinstance(f, dict)]
    if isinstance(payload, list):
        return [f for f in payload if isinstance(f, dict)]
    raise ProviderError(f"extraction response not shaped as {{facts: [...]}}: {payload!r:.200}")


async def extract_from_chunk(
    chunk: Chunk,
    provider: LLMProvider,
    *,
    document_id: str | None = None,
) -> tuple[list[AnchoredFact], ExtractionStats]:
    stats = ExtractionStats(chunks_seen=1)
    if len(chunk.text.strip()) < _MIN_CHUNK_CHARS and not chunk.table_markdown:
        return [], stats

    stats.chunks_called = 1
    user_prompt = build_user_prompt(chunk)
    try:
        result = await provider.complete(
            CompletionRequest(
                system=SYSTEM_PROMPT,
                user=user_prompt,
                json_schema=EXTRACTION_JSON_SCHEMA,
                temperature=0.0,
            )
        )
        stats.llm_calls = 1
        raw_facts = _parse_facts(result.json())
    except ProviderError as exc:
        if _is_schema_rejection(exc):
            # Provider will not accept this structured-output schema; fall back to
            # a plain JSON instruction so the pipeline still runs.
            logger.warning(
                "provider rejected the extraction schema, retrying unconstrained: %s", exc
            )
            try:
                result = await provider.complete(
                    CompletionRequest(
                        system=SYSTEM_PROMPT + _JSON_FALLBACK_INSTRUCTION,
                        user=user_prompt,
                        temperature=0.0,
                    )
                )
                stats.llm_calls = 1
                raw_facts = _parse_facts(result.json())
            except ProviderError as exc2:
                logger.warning("extraction failed on chunk %d: %s", chunk.index, exc2)
                stats.chunks_failed = 1
                return [], stats
        else:
            logger.warning("extraction failed on chunk %d: %s", chunk.index, exc)
            stats.chunks_failed = 1
            return [], stats

    stats.facts_returned = len(raw_facts)
    anchored: list[AnchoredFact] = []

    for raw in raw_facts:
        try:
            fact = CandidateFact.model_validate(raw)
        except ValidationError as exc:
            logger.debug("invalid candidate fact on chunk %d: %s", chunk.index, exc)
            stats.dropped_invalid += 1
            continue

        if repair_comparator(fact):
            stats.comparator_repaired += 1

        if (
            chunk.table_markdown
            and fact.fact_kind is FactKind.quantitative
            and not _has_column_context(fact)
        ):
            stats.dropped_no_column_context += 1
            continue

        fact.extraction_confidence = min(fact.extraction_confidence, chunk.confidence_ceiling)

        anchor = anchor_evidence(chunk, fact.evidence_text)
        notes: list[str] = []
        if anchor is None:
            stats.unanchored += 1
            notes.append("evidence span not found in the source chunk")
        elif not anchor.exact:
            notes.append("evidence matched after whitespace/quote normalization")

        anchored.append(
            AnchoredFact(candidate=fact, anchor=anchor, document_id=document_id, notes=notes)
        )
        stats.facts_kept += 1
        stats.by_kind[fact.fact_kind.value] = stats.by_kind.get(fact.fact_kind.value, 0) + 1

    return anchored, stats


def _merge_stats(into: ExtractionStats, other: ExtractionStats) -> None:
    into.chunks_seen += other.chunks_seen
    into.chunks_called += other.chunks_called
    into.chunks_failed += other.chunks_failed
    into.llm_calls += other.llm_calls
    into.facts_returned += other.facts_returned
    into.facts_kept += other.facts_kept
    into.unanchored += other.unanchored
    into.dropped_no_column_context += other.dropped_no_column_context
    into.dropped_invalid += other.dropped_invalid
    into.comparator_repaired += other.comparator_repaired
    for k, v in other.by_kind.items():
        into.by_kind[k] = into.by_kind.get(k, 0) + v


@dataclass(frozen=True, slots=True)
class ExtractionProgress:
    """Reported once per chunk as extraction runs, so a caller can surface a
    live counter instead of a silent wait."""

    pages_done: int
    pages_total: int
    facts_so_far: int
    last_page: int | None


ProgressCallback = Callable[[ExtractionProgress], Awaitable[None]]


async def extract_document(
    ingestion: IngestionResult,
    *,
    provider: LLMProvider | None = None,
    document_id: str | None = None,
    concurrency: int = 3,
    max_chunks: int | None = None,
    pages: Iterable[int] | None = None,
    on_progress: ProgressCallback | None = None,
) -> ExtractionResult:
    provider = provider or get_llm_provider()
    chunks: Sequence[Chunk] = ingestion.chunks
    if pages is not None:
        wanted = set(pages)
        chunks = [c for c in chunks if c.page_number in wanted]
    if max_chunks is not None:
        chunks = list(chunks)[:max_chunks]

    semaphore = asyncio.Semaphore(max(1, concurrency))
    total = len(chunks)
    progress_lock = asyncio.Lock()
    done = 0
    facts_so_far = 0

    async def _run(chunk: Chunk) -> tuple[list[AnchoredFact], ExtractionStats]:
        nonlocal done, facts_so_far
        async with semaphore:
            out = await extract_from_chunk(chunk, provider, document_id=document_id)
        if on_progress is not None:
            async with progress_lock:
                done += 1
                facts_so_far += len(out[0])
                snapshot = ExtractionProgress(done, total, facts_so_far, chunk.page_number)
            try:
                await on_progress(snapshot)
            except Exception:  # noqa: BLE001 - progress reporting must never break extraction
                logger.debug("extraction progress callback failed", exc_info=True)
        return out

    results = await asyncio.gather(*(_run(c) for c in chunks))

    facts: list[AnchoredFact] = []
    totals = ExtractionStats()
    for chunk_facts, chunk_stats in results:
        facts.extend(chunk_facts)
        _merge_stats(totals, chunk_stats)

    logger.info(
        "extracted %d fact(s) from %s over %d chunk(s), %d LLM call(s)",
        totals.facts_kept,
        ingestion.filename,
        totals.chunks_called,
        totals.llm_calls,
    )
    return ExtractionResult(
        document_filename=ingestion.filename,
        content_hash=ingestion.content_hash,
        facts=facts,
        stats=totals,
    )

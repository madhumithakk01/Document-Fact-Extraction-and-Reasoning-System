"""Run the schema-constrained extraction call over a document's chunks.

Consecutive text pages are batched into one model call (the fixed system-prompt
and schema overhead is paid once per batch, not once per page); table pages are
called on their own so their column/row rules stay isolated. Each returned fact
is validated, run through the deterministic comparator safety net, checked for
table column context, anchored to the page it names, and capped at that page's
confidence ceiling. Output is unverified ``AnchoredFact``s.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from app.extraction.anchoring import anchor_evidence, normalize_for_match
from app.extraction.prompts import (
    BATCH_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_batch_user_prompt,
    build_user_prompt,
)
from app.extraction.schema import (
    BATCH_EXTRACTION_JSON_SCHEMA,
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
from app.providers.base import (
    AllProvidersUnavailable,
    CompletionRequest,
    LLMProvider,
    ProviderError,
)

logger = logging.getLogger(__name__)

_MIN_CHUNK_CHARS = 40
_COLUMN_QUALIFIER_KEYS = ("column_header", "column", "col_header", "col")

# Batch sizing: keep one call's page text well under the token ceiling so that,
# with ~3.4k tokens of fixed system-prompt + schema overhead, the whole call
# stays near 6k tokens.
_BATCH_MAX_PAGES = 6
_BATCH_CHAR_BUDGET = 10_000

_JSON_FALLBACK_INSTRUCTION = (
    '\n\nReturn ONLY a JSON object of the form {"facts": [ ... ]}. Each fact has '
    "fact_kind, entity, entity_resolved, attribute, value (object with comparator, "
    "number, number_high, unit, state, text), period (object with raw_label, "
    "start_date, end_date), qualifiers (list of {name, value}), evidence_text, "
    "extraction_confidence, and source_page (the number from the '=== PAGE N ===' "
    "header of the page the evidence was copied from, or null if only one page is "
    "shown). No prose, no markdown fences."
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


# Approximate-language cues are only trusted when they sit next to the fact's own
# number: scanning the whole evidence span lets "more than" from a neighbouring
# clause flip an exact figure to an inequality.
_LEFT_WINDOW = 24
_RIGHT_WINDOW = 16
_CLAUSE_BOUNDARY_CHARS = ";:.()[]{}–—,"


def _number_forms(number: float) -> list[str]:
    """Plausible written forms of ``number`` (grouped and plain), longest first."""
    forms: set[str] = set()
    magnitude = abs(number)
    if magnitude == int(magnitude):
        n = int(magnitude)
        forms.update((str(n), f"{n:,}"))
    else:
        forms.update((repr(magnitude), f"{magnitude:,}", f"{magnitude:.2f}", f"{magnitude:,.2f}"))
    return sorted(forms, key=len, reverse=True)


def _locate_number(evidence: str, number: float) -> tuple[int, int] | None:
    for form in _number_forms(number):
        start = 0
        while (i := evidence.find(form, start)) != -1:
            before = evidence[i - 1] if i > 0 else ""
            after_at = i + len(form)
            after = evidence[after_at] if after_at < len(evidence) else ""
            if not before.isdigit() and not after.isdigit() and after not in ".,":
                return i, after_at
            start = i + 1
    return None


def _clause_around_number(evidence: str, number: float) -> str | None:
    """The stretch of evidence immediately around where ``number`` is written,
    clipped at the nearest clause punctuation and a short character window."""
    span = _locate_number(evidence, number)
    if span is None:
        return None
    lo, hi = span
    left_bounds = [
        i for i in (evidence.rfind(ch, 0, lo) for ch in _CLAUSE_BOUNDARY_CHARS) if i != -1
    ]
    left_start = max([lo - _LEFT_WINDOW, 0, *(i + 1 for i in left_bounds)])
    right_bounds = [
        i for i in (evidence.find(ch, hi) for ch in _CLAUSE_BOUNDARY_CHARS) if i != -1
    ]
    right_end = min([hi + _RIGHT_WINDOW, len(evidence), *right_bounds])
    return evidence[left_start:right_end]


def repair_comparator(fact: CandidateFact) -> bool:
    """Deterministic backstop for §6.2: approximated language must never read as
    exact equality. Returns True if the comparator was changed."""
    if fact.fact_kind is not FactKind.quantitative:
        return False
    current = fact.value.comparator
    if current not in (None, Comparator.eq):
        return False

    haystack = fact.evidence_text
    if fact.value.number is not None:
        clause = _clause_around_number(fact.evidence_text, fact.value.number)
        if clause is not None:
            haystack = clause

    for pattern, comparator in _APPROX_PATTERNS:
        if pattern.search(haystack):
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


def _finalize_candidate(
    raw: dict,
    chunk: Chunk,
    *,
    document_id: str | None,
    stats: ExtractionStats,
    provider_used: str | None = None,
) -> AnchoredFact | None:
    """Validate one raw fact against ``chunk`` and anchor its evidence, updating
    ``stats``. Returns None when the fact is dropped."""
    try:
        fact = CandidateFact.model_validate(raw)
    except ValidationError as exc:
        logger.debug("invalid candidate fact on page %d: %s", chunk.page_number, exc)
        stats.dropped_invalid += 1
        return None

    if repair_comparator(fact):
        stats.comparator_repaired += 1

    if (
        chunk.table_markdown
        and fact.fact_kind is FactKind.quantitative
        and not _has_column_context(fact)
    ):
        stats.dropped_no_column_context += 1
        return None

    fact.extraction_confidence = min(fact.extraction_confidence, chunk.confidence_ceiling)

    anchor = anchor_evidence(chunk, fact.evidence_text)
    notes: list[str] = []
    if anchor is None:
        stats.unanchored += 1
        notes.append("evidence span not found in the source chunk")
    elif not anchor.exact:
        notes.append("evidence matched after whitespace/quote normalization")

    stats.facts_kept += 1
    stats.by_kind[fact.fact_kind.value] = stats.by_kind.get(fact.fact_kind.value, 0) + 1
    return AnchoredFact(
        candidate=fact,
        anchor=anchor,
        document_id=document_id,
        notes=notes,
        provider_used=provider_used,
    )


def _resolve_batch_chunk(raw: dict, chunks: Sequence[Chunk], by_page: dict[int, Chunk]) -> Chunk:
    """Pick the page a batched fact belongs to: its stated ``source_page`` when
    that is one of the batch's pages, otherwise the page whose text contains the
    evidence span, otherwise the first page (anchoring will then flag it)."""
    sp = raw.get("source_page")
    if isinstance(sp, int) and sp in by_page:
        return by_page[sp]
    evidence = str(raw.get("evidence_text") or "").strip()
    if evidence:
        norm = normalize_for_match(evidence)
        for chunk in chunks:
            if evidence in chunk.text or (norm and norm in normalize_for_match(chunk.text)):
                return chunk
    return chunks[0]


def _plan_batches(
    chunks: Sequence[Chunk],
    *,
    max_pages: int = _BATCH_MAX_PAGES,
    char_budget: int = _BATCH_CHAR_BUDGET,
) -> list[list[Chunk]]:
    """Group consecutive text pages so one call covers several; every table page
    is its own batch so its column/row rules are not diluted by other pages."""
    batches: list[list[Chunk]] = []
    current: list[Chunk] = []
    current_chars = 0

    def _flush() -> None:
        nonlocal current, current_chars
        if current:
            batches.append(current)
            current = []
            current_chars = 0

    for chunk in chunks:
        if chunk.table_markdown:
            _flush()
            batches.append([chunk])
            continue
        size = len(chunk.text)
        if current and (len(current) >= max_pages or current_chars + size > char_budget):
            _flush()
        current.append(chunk)
        current_chars += size
    _flush()
    return batches


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
    except AllProvidersUnavailable:
        raise  # every provider failed -> surfaced as extraction_unavailable, not a swallowed miss
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
            except AllProvidersUnavailable:
                raise
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
        af = _finalize_candidate(
            raw, chunk, document_id=document_id, stats=stats, provider_used=result.provider
        )
        if af is not None:
            anchored.append(af)
    return anchored, stats


async def extract_from_batch(
    chunks: Sequence[Chunk],
    provider: LLMProvider,
    *,
    document_id: str | None = None,
) -> tuple[list[AnchoredFact], ExtractionStats]:
    """One model call over several text pages. Each returned fact names the page
    it came from; it is validated and anchored against that page's chunk."""
    stats = ExtractionStats(chunks_seen=len(chunks))
    usable = [c for c in chunks if len(c.text.strip()) >= _MIN_CHUNK_CHARS or c.table_markdown]
    if not usable:
        return [], stats

    pages = [c.page_number for c in chunks]
    stats.chunks_called = len(chunks)
    user_prompt = build_batch_user_prompt(list(chunks))
    try:
        result = await provider.complete(
            CompletionRequest(
                system=BATCH_SYSTEM_PROMPT,
                user=user_prompt,
                json_schema=BATCH_EXTRACTION_JSON_SCHEMA,
                temperature=0.0,
            )
        )
        stats.llm_calls = 1
        raw_facts = _parse_facts(result.json())
    except AllProvidersUnavailable:
        raise  # every provider failed -> surfaced as extraction_unavailable, not a swallowed miss
    except ProviderError as exc:
        if _is_schema_rejection(exc):
            logger.warning("provider rejected the batch schema, retrying unconstrained: %s", exc)
            try:
                result = await provider.complete(
                    CompletionRequest(
                        system=BATCH_SYSTEM_PROMPT + _JSON_FALLBACK_INSTRUCTION,
                        user=user_prompt,
                        temperature=0.0,
                    )
                )
                stats.llm_calls = 1
                raw_facts = _parse_facts(result.json())
            except AllProvidersUnavailable:
                raise
            except ProviderError as exc2:
                logger.warning("batch extraction failed on pages %s: %s", pages, exc2)
                stats.chunks_failed = len(chunks)
                return [], stats
        else:
            logger.warning("batch extraction failed on pages %s: %s", pages, exc)
            stats.chunks_failed = len(chunks)
            return [], stats

    stats.facts_returned = len(raw_facts)
    by_page = {c.page_number: c for c in chunks}
    anchored: list[AnchoredFact] = []
    for raw in raw_facts:
        chunk = _resolve_batch_chunk(raw, chunks, by_page)
        af = _finalize_candidate(
            raw, chunk, document_id=document_id, stats=stats, provider_used=result.provider
        )
        if af is not None:
            anchored.append(af)
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

    batches = _plan_batches(chunks)
    semaphore = asyncio.Semaphore(max(1, concurrency))
    total = len(chunks)
    progress_lock = asyncio.Lock()
    done = 0
    facts_so_far = 0

    async def _run(batch: list[Chunk]) -> tuple[list[AnchoredFact], ExtractionStats]:
        nonlocal done, facts_so_far
        async with semaphore:
            if batch[0].table_markdown:
                out = await extract_from_chunk(batch[0], provider, document_id=document_id)
            else:
                out = await extract_from_batch(batch, provider, document_id=document_id)
        if on_progress is not None:
            async with progress_lock:
                done += len(batch)
                facts_so_far += len(out[0])
                snapshot = ExtractionProgress(done, total, facts_so_far, batch[-1].page_number)
            try:
                await on_progress(snapshot)
            except Exception:  # noqa: BLE001 - progress reporting must never break extraction
                logger.debug("extraction progress callback failed", exc_info=True)
        return out

    results = await asyncio.gather(*(_run(b) for b in batches))

    facts: list[AnchoredFact] = []
    totals = ExtractionStats()
    for chunk_facts, chunk_stats in results:
        facts.extend(chunk_facts)
        _merge_stats(totals, chunk_stats)

    logger.info(
        "extracted %d fact(s) from %s over %d page(s) in %d batch(es), %d LLM call(s)",
        totals.facts_kept,
        ingestion.filename,
        totals.chunks_called,
        len(batches),
        totals.llm_calls,
    )
    return ExtractionResult(
        document_filename=ingestion.filename,
        content_hash=ingestion.content_hash,
        facts=facts,
        stats=totals,
    )

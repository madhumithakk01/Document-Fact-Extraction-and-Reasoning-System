from __future__ import annotations

import re

from app.extraction.extractor import extract_document, extract_from_chunk
from app.extraction.schema import ExtractionStats
from app.ingestion.types import DocumentContentType, DocumentProfile, IngestionResult
from tests.extraction.conftest import fact_payload, failing_provider, make_provider


async def test_returns_anchored_fact(make_chunk) -> None:
    text = "In FY24, consolidated revenue was INR 8,142 Crore, up sharply."
    chunk = make_chunk(text, char_start=2000)
    provider = make_provider(
        {"facts": [fact_payload(evidence_text="consolidated revenue was INR 8,142 Crore")]}
    )

    facts, stats = await extract_from_chunk(chunk, provider)

    assert len(facts) == 1
    af = facts[0]
    assert af.candidate.entity == "Acme Corporation"
    assert af.anchored and af.anchor.exact
    assert af.anchor.char_start == 2000 + text.index("consolidated revenue")
    assert stats.facts_kept == 1
    assert stats.by_kind == {"quantitative": 1}


async def test_invalid_fact_is_dropped(make_chunk) -> None:
    chunk = make_chunk("some page text about the company and its revenue of 10 crore")
    provider = make_provider({"facts": [fact_payload(), fact_payload(entity="   ", attribute="")]})
    facts, stats = await extract_from_chunk(chunk, provider)
    assert stats.facts_returned == 2
    assert stats.dropped_invalid == 1
    assert len(facts) == 1


async def test_table_fact_without_column_context_is_dropped(make_chunk) -> None:
    chunk = make_chunk(
        "Revenue 8,142 EBITDA 127",
        table_markdown="| Metric | FY24 |\n| --- | --- |\n| Revenue | 8,142 |",
    )
    provider = make_provider(
        {
            "facts": [
                fact_payload(evidence_text="Revenue 8,142", qualifiers={"basis": "consolidated"}),
                fact_payload(
                    evidence_text="Revenue 8,142",
                    qualifiers={"column_header": "FY24", "row_header": "Revenue"},
                ),
            ]
        }
    )
    facts, stats = await extract_from_chunk(chunk, provider)
    assert stats.dropped_no_column_context == 1
    assert len(facts) == 1
    assert facts[0].candidate.qualifiers["column_header"] == "FY24"


async def test_confidence_capped_at_chunk_ceiling(make_chunk) -> None:
    chunk = make_chunk("OCR page text mentioning revenue of 8,142 crore", confidence_ceiling=0.6)
    provider = make_provider(
        {
            "facts": [
                fact_payload(evidence_text="revenue of 8,142 crore", extraction_confidence=0.95)
            ]
        }
    )
    facts, _ = await extract_from_chunk(chunk, provider)
    assert facts[0].candidate.extraction_confidence == 0.6


async def test_unanchored_fact_kept_with_note(make_chunk) -> None:
    chunk = make_chunk("This page does not contain the quoted sentence at all.")
    provider = make_provider(
        {"facts": [fact_payload(evidence_text="a sentence that is nowhere on the page")]}
    )
    facts, stats = await extract_from_chunk(chunk, provider)
    assert stats.unanchored == 1
    assert not facts[0].anchored
    assert any("not found" in n for n in facts[0].notes)


async def test_comparator_repaired_counter(make_chunk) -> None:
    text = "The company delivered over 2,800 million shipments since inception."
    chunk = make_chunk(text)
    provider = make_provider(
        {
            "facts": [
                fact_payload(
                    fact_kind="quantitative",
                    attribute="cumulative shipments",
                    evidence_text="delivered over 2,800 million shipments",
                    value={"comparator": "eq", "number": 2800.0, "unit": "million"},
                )
            ]
        }
    )
    facts, stats = await extract_from_chunk(chunk, provider)
    assert stats.comparator_repaired == 1
    assert facts[0].candidate.value.comparator.value == "gt"


async def test_provider_failure_is_contained(make_chunk) -> None:
    chunk = make_chunk("page text long enough to be worth a call about revenue")
    facts, stats = await extract_from_chunk(chunk, failing_provider())
    assert facts == []
    assert stats.chunks_failed == 1
    assert stats.llm_calls == 0


async def test_short_chunk_is_skipped_without_a_call(make_chunk) -> None:
    provider = make_provider({"facts": [fact_payload()]})
    facts, stats = await extract_from_chunk(make_chunk("Contents"), provider)
    assert facts == []
    assert stats.chunks_called == 0
    assert provider.calls == []


def _ingestion(chunks) -> IngestionResult:
    return IngestionResult(
        filename="doc.pdf",
        content_hash="deadbeef",
        profile=DocumentProfile(
            content_type=DocumentContentType.text_native,
            page_count=len(chunks),
            pages_text_native=len(chunks),
            pages_table_heavy=0,
            pages_image_only=0,
            pages_empty=0,
            ocr_pages=0,
        ),
        pages=[],
        chunks=chunks,
    )


_PAGE_RE = re.compile(r"=== PAGE (\d+) ===")


def _one_fact_per_page(request) -> dict:  # type: ignore[no-untyped-def]
    """A responder that reads the '=== PAGE N ===' headers in the batched prompt
    and returns one fact per page, each tagged with its source_page."""
    seen = [int(n) for n in _PAGE_RE.findall(request.user)]
    return {
        "facts": [
            fact_payload(evidence_text=f"revenue was {n}00 crore", source_page=n) for n in seen
        ]
    }


async def test_extract_document_batches_text_pages_into_one_call(make_chunk) -> None:
    chunks = [
        make_chunk(
            f"Page {i} states revenue was {i}00 crore this year.", index=i - 1, page_number=i
        )
        for i in range(1, 6)
    ]
    provider = make_provider(_one_fact_per_page)

    full = await extract_document(_ingestion(chunks), provider=provider, concurrency=2)
    assert full.stats.chunks_called == 5  # all five pages covered
    assert full.stats.llm_calls == 1  # in a single batched call
    assert full.stats.facts_kept == 5  # one fact per page, each anchored to its page
    assert {af.anchor.page_number for af in full.facts} == {1, 2, 3, 4, 5}

    limited = await extract_document(
        _ingestion(chunks), provider=make_provider(_one_fact_per_page), max_chunks=2
    )
    assert limited.stats.chunks_called == 2

    paged = await extract_document(
        _ingestion(chunks), provider=make_provider(_one_fact_per_page), pages=[2, 4]
    )
    assert paged.stats.chunks_called == 2
    assert {af.anchor.page_number for af in paged.facts} == {2, 4}


async def test_table_pages_are_extracted_on_their_own(make_chunk) -> None:
    chunks = [
        make_chunk("Page 1 narrative about revenue of 100 crore.", index=0, page_number=1),
        make_chunk(
            "Revenue 8,142 EBITDA 127",
            index=1,
            page_number=2,
            table_markdown="| Metric | FY24 |\n| --- | --- |\n| Revenue | 8,142 |",
        ),
        make_chunk("Page 3 narrative about margin of 1.6%.", index=2, page_number=3),
    ]
    calls: list[str] = []

    def _responder(request) -> dict:  # type: ignore[no-untyped-def]
        calls.append(request.system)
        return {"facts": []}

    await extract_document(_ingestion(chunks), provider=make_provider(_responder), concurrency=1)

    # one call for the table page, one batched call for the two narrative pages
    assert len(calls) == 2


async def test_extract_document_reports_progress_per_batch(make_chunk) -> None:
    chunks = [
        make_chunk(
            f"Page {i} of the report states revenue was {i}00 crore this year.",
            index=i - 1,
            page_number=i,
        )
        for i in range(1, 9)
    ]
    provider = make_provider(_one_fact_per_page)

    seen: list[tuple[int, int, int]] = []

    async def _on_progress(p) -> None:  # type: ignore[no-untyped-def]
        seen.append((p.pages_done, p.pages_total, p.facts_so_far))

    await extract_document(
        _ingestion(chunks), provider=provider, concurrency=1, on_progress=_on_progress
    )

    # eight pages, batched 6 + 2, so progress is reported twice
    assert [d for d, _, _ in seen] == [6, 8]
    assert all(total == 8 for _, total, _ in seen)
    assert [f for _, _, f in seen] == [6, 8]


def test_stats_merge_is_additive() -> None:
    a = ExtractionStats(facts_kept=2, by_kind={"quantitative": 2})
    b = ExtractionStats(facts_kept=1, by_kind={"status": 1, "quantitative": 1})
    from app.extraction.extractor import _merge_stats

    _merge_stats(a, b)
    assert a.facts_kept == 3
    assert a.by_kind == {"quantitative": 3, "status": 1}

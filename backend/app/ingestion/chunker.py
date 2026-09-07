"""Page-level chunking with trailing-context carryover.

One chunk per page that has extractable content. Each chunk carries roughly
150-200 tokens from the tail of the previous chunk so that pronouns, running
sentences, and table headers split across a page break still resolve when the
chunk is handed to extraction. The carried text is context only -- it is never
re-extracted from, to avoid emitting the same fact on two consecutive pages.
"""

from __future__ import annotations

from app.ingestion.tokens import tail_by_tokens
from app.ingestion.types import Chunk, PageContentType, ParsedPage

CARRYOVER_TOKENS = 175


def build_chunks(pages: list[ParsedPage], carryover_tokens: int = CARRYOVER_TOKENS) -> list[Chunk]:
    chunks: list[Chunk] = []
    cursor = 0
    previous_text = ""
    index = 0
    for page in pages:
        page_text = page.text.strip()
        # Blank pages produce nothing. An image-only page with no recovered text
        # is still emitted as a chunk (empty body, image kept) so the page is
        # represented downstream rather than silently missing.
        drop = page.content_type == PageContentType.empty or (
            not page_text and page.content_type != PageContentType.image_only
        )
        if drop:
            cursor += len(page.text) + 2  # keep later offsets aligned
            continue

        table_md = None
        if page.tables:
            table_md = "\n\n".join(t.to_markdown() for t in page.tables)

        char_start = cursor
        char_end = cursor + len(page_text)
        chunks.append(
            Chunk(
                page_number=page.page_number,
                index=index,
                text=page_text,
                leading_context=tail_by_tokens(previous_text, carryover_tokens)
                if previous_text
                else "",
                char_start=char_start,
                char_end=char_end,
                has_table=page.has_table,
                table_markdown=table_md,
                image_ref=page.image_ref,
                content_type=page.content_type,
                confidence_ceiling=page.confidence_ceiling,
            )
        )
        cursor = char_end + 2
        if page_text:  # carry context across a textless image page
            previous_text = page_text
        index += 1
    return chunks

"""Prompt construction for the extraction call.

The system prompt fixes the extraction contract; the user prompt is just the
chunk (with carried context and, for table pages, the reconstructed grid). No
domain, metric list, or entity vocabulary is baked in.
"""

from __future__ import annotations

from app.ingestion.types import Chunk

SYSTEM_PROMPT = """\
You extract atomic, independently verifiable facts from one page of a document.

An atomic fact is a single claim about one entity: one measurement, one status, \
or one qualitative assertion. Split compound sentences into separate facts. Do \
not infer, aggregate, or compute values that are not written on the page.

Extract ONLY facts stated on the current page. Any text under \
"[continued from previous page]" is context for resolving pronouns and \
references - never extract a fact whose wording appears only there. Every \
evidence_text you return must be copyable verbatim from the current page.

For every fact:
- entity: the specific subject. Resolve "the Company", "it", "the group", and \
pronouns using the [continued from previous page] context when present. Set \
entity_resolved to false when you had to rely on that carried context.
- attribute: what is measured or asserted, in open vocabulary. Keep the \
document's own wording (e.g. "consolidated EBITDA", not "profit").
- fact_kind: "quantitative" for a number, "status" for a state \
(profitable / listed / approved / discontinued), "qualitative" for a \
descriptive claim with no number or discrete state.
- value.comparator (quantitative only): never assume "eq". "over" / "more than" \
-> gt; "at least" / "minimum" -> gte; "up to" / "no more than" -> lte; \
"under" / "less than" -> lt; "about" / "around" / "approximately" / "~" / \
"nearly" -> approx; an explicit low-to-high band -> range (fill number and \
number_high).
- value.unit: copy the unit exactly as written, including scale words \
("Crore", "Lakh", "Million", "bn").
- period.raw_label: the period exactly as written. Only fill start_date / \
end_date if the page (or its context) states the fiscal-year convention.
- qualifiers: a list of {name, value} pairs capturing anything needed to \
compare the fact fairly later - basis, currency, audited vs unaudited, actual \
vs forecast, standalone vs consolidated, who is asserting it. For any value \
taken from a table you MUST include a pair named "column_header" and one named \
"row_header". Use an empty list if nothing applies.
- evidence_text: a continuous run of text copied verbatim from the current \
page. Never paraphrase or reorder. Make it long enough that the entity and \
attribute are clear from the span alone - quote the label together with its \
number (e.g. "Rs.127Cr / 1.6% EBITDA / EBITDA margin"), not the bare number.
- extraction_confidence: 0-1, your confidence that this fact is correct and \
complete as written.

Return only facts actually stated on the page. If the page is a cover, table of \
contents, or has no factual content, return an empty list.\
"""


def build_user_prompt(chunk: Chunk) -> str:
    parts: list[str] = []
    if chunk.leading_context:
        parts.append(f"[continued from previous page]\n{chunk.leading_context}")
        parts.append("[current page]")
    parts.append(chunk.text)
    if chunk.table_markdown:
        parts.append(
            "\n[reconstructed table(s) on this page - use these for column and row headers]\n"
            + chunk.table_markdown
        )
    if chunk.confidence_ceiling < 1.0:
        parts.append(
            f"\n[note] This page was read with reduced reliability "
            f"(ceiling {chunk.confidence_ceiling:.2f}); keep extraction_confidence at or below it."
        )
    return "\n".join(parts)

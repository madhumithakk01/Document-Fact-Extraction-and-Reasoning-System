"""Independent verification prompt (§6.3 step 2).

The verifier gets the structured claim and the cited span only -- no page, no
surrounding paragraphs, no other facts. It judges whether that span, on its own,
states this exact claim.
"""

from __future__ import annotations

from typing import Any

from app.extraction.schema import CandidateFact

INDEPENDENT_VERIFY_SYSTEM = """\
You are a strict fact checker. You are given ONE claim and the exact quoted \
span it was drawn from. You have no other context and must not assume any.

Decide whether the quoted span, by itself, states this exact claim:
- entity: is the span about this specific subject?
- attribute: does the span assert this specific measure or property?
- value: does the span state this number / state / text, with this comparator \
(eq means an exact stated figure; gt/gte/lt/lte/approx/range must match the \
span's own wording) and this unit (including scale words like Crore, Million)?
- period: does the span attach the value to this period?

Return verdict = "supported" only if entity, attribute, value, unit, comparator, \
and period are all borne out by the span. Use "partially_supported" if the core \
claim holds but a detail (unit, period, comparator) is wrong or missing. Use \
"not_supported" if the span does not state this claim at all or contradicts it.

For every discrepancy add an issue naming the field ("entity", "attribute", \
"value.number", "value.unit", "value.comparator", "period", or "other"), the \
problem, and, only when the span itself makes the right value unambiguous, a \
suggested_correction as a short literal string. Do not guess corrections.

supported_confidence is your confidence (0-1) that verdict = "supported" is the \
correct call for this span.\
"""

INDEPENDENT_VERIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["supported", "partially_supported", "not_supported"],
        },
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "field": {"type": "string"},
                    "problem": {"type": "string"},
                    "suggested_correction": {"type": ["string", "null"]},
                },
                "required": ["field", "problem", "suggested_correction"],
            },
        },
        "supported_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning": {"type": "string"},
    },
    "required": ["verdict", "issues", "supported_confidence", "reasoning"],
}


def render_claim(fact: CandidateFact) -> str:
    v = fact.value
    lines = [
        f"fact_kind: {fact.fact_kind.value}",
        f"entity: {fact.entity}",
        f"attribute: {fact.attribute}",
    ]
    if fact.fact_kind.value == "quantitative":
        lines.append(f"comparator: {v.comparator.value if v.comparator else '(none)'}")
        lines.append(f"number: {v.number if v.number is not None else '(none)'}")
        if v.number_high is not None:
            lines.append(f"number_high: {v.number_high}")
        lines.append(f"unit: {v.unit or '(none)'}")
    elif fact.fact_kind.value == "status":
        lines.append(f"state: {v.state or '(none)'}")
    else:
        lines.append(f"text: {v.text or '(none)'}")
    lines.append(f"period: {fact.period.raw_label or '(none)'}")
    if fact.qualifiers:
        pairs = ", ".join(f"{k}={val}" for k, val in fact.qualifiers.items())
        lines.append(f"qualifiers: {pairs}")
    return "\n".join(lines)


def build_verify_prompt(fact: CandidateFact, cited_span: str) -> str:
    return (
        "CLAIM\n"
        f"{render_claim(fact)}\n\n"
        "CITED SPAN (verbatim, the only evidence you have)\n"
        f'"""{cited_span.strip()}"""\n'
    )

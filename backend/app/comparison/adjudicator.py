"""The adjudication call (§6.5).

Given two facts and their verbatim evidence, reason through -- in this order --
entity match, attribute match, period overlap (allowing for different fiscal-year
or calendar conventions), unit and scale conversion, scope/qualifier
explanation, and comparator consistency, then classify the pair. Never pick a
side between two disagreeing sources: a real contradiction is a valid answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.comparison.precheck import ComparableFact
from app.providers.base import CompletionRequest, LLMProvider, ProviderError


class RelationshipType(StrEnum):
    corroborates = "corroborates"
    contradicts = "contradicts"
    reconciled_by_context = "reconciled_by_context"
    unrelated = "unrelated"


@dataclass(frozen=True, slots=True)
class Adjudication:
    relationship_type: RelationshipType
    reconciliation_basis: str | None
    explanation: str
    confidence: float
    needs_more_context: bool
    missing_context: str | None
    reasoning: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: dict) -> Adjudication:
        rt = RelationshipType(payload["relationship_type"])
        basis = payload.get("reconciliation_basis") or None
        return cls(
            relationship_type=rt,
            reconciliation_basis=basis if rt is RelationshipType.reconciled_by_context else None,
            explanation=str(payload.get("explanation") or "").strip(),
            confidence=max(0.0, min(1.0, float(payload.get("confidence", 0.0)))),
            needs_more_context=bool(payload.get("needs_more_context")),
            missing_context=(payload.get("missing_context") or None),
            reasoning={
                k: payload.get(k)
                for k in (
                    "entity_match",
                    "attribute_match",
                    "period_relation",
                    "unit_scale_note",
                    "qualifier_explanation",
                    "comparator_consistent",
                )
            },
        )


SYSTEM_PROMPT = """\
You compare two facts drawn from documents in one project and decide how they
relate. Work through these in order and let them drive the verdict:

1. entity_match - are both facts about the same specific subject?
2. attribute_match - the same measure or property?
3. period_relation - do the periods refer to the same span? Treat "FY24",
   "FY2023-24", and "year ended March 31, 2024" as the same; a quarter inside a
   year is "a_within_b" / "b_within_a".
4. unit_scale_note - convert scales (Crore, Lakh, Million, bn) and note whether
   the figures then agree.
5. qualifier_explanation - do differing qualifiers (basis, currency, audited,
   consolidated vs standalone, actual vs forecast, who is asserting) explain a
   gap between the values?
6. comparator_consistent - are the comparators ("over", "about", exact) mutually
   satisfiable?

Then classify:
- corroborates: same subject, period, and (after scaling) value; nothing
  material differs.
- contradicts: same subject and period, values genuinely disagree, and no
  qualifier or convention explains it. Report this plainly; do not average or
  pick a side.
- reconciled_by_context: the values differ but a specific, named basis explains
  it (different period, currency, scope, rounding, consolidation, ...). Put that
  basis in reconciliation_basis.
- unrelated: not the same subject or attribute, or not comparable at all.

Set needs_more_context true only if a targeted lookup in the other documents
could change the verdict; say what you would look for in missing_context.
confidence is 0-1 for the verdict you gave.\
"""

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "entity_match": {"type": "boolean"},
        "attribute_match": {"type": "boolean"},
        "period_relation": {
            "type": "string",
            "enum": ["same", "a_within_b", "b_within_a", "overlapping", "disjoint", "unclear"],
        },
        "unit_scale_note": {"type": "string"},
        "qualifier_explanation": {"type": "string"},
        "comparator_consistent": {"type": "boolean"},
        "relationship_type": {
            "type": "string",
            "enum": ["corroborates", "contradicts", "reconciled_by_context", "unrelated"],
        },
        "reconciliation_basis": {"type": ["string", "null"]},
        "explanation": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "needs_more_context": {"type": "boolean"},
        "missing_context": {"type": ["string", "null"]},
    },
    "required": [
        "entity_match",
        "attribute_match",
        "period_relation",
        "unit_scale_note",
        "qualifier_explanation",
        "comparator_consistent",
        "relationship_type",
        "reconciliation_basis",
        "explanation",
        "confidence",
        "needs_more_context",
        "missing_context",
    ],
}


_TRIPLE_QUOTE_RUN = re.compile(r'"{3,}')


def _fence_evidence(evidence: str) -> str:
    """Quote evidence so a stray triple-quote in the source text cannot be read
    as the closing delimiter: collapse any run of 3+ double-quotes and keep a
    space between the body and each fence."""
    body = _TRIPLE_QUOTE_RUN.sub('""', evidence.strip())
    return f'""" {body} """'


def _render(tag: str, fact: ComparableFact, evidence: str) -> str:
    v = fact.value
    if fact.fact_kind == "quantitative":
        val = f"{v.get('comparator', 'eq')} {v.get('number', '?')}"
        if v.get("number_high") is not None:
            val += f"..{v['number_high']}"
        val += f" {v.get('unit') or ''}"
    else:
        val = v.get("state") or v.get("text") or "?"
    quals = ", ".join(f"{k}={x}" for k, x in (fact.qualifiers or {}).items()) or "(none)"
    return (
        f"FACT {tag}\n"
        f"  entity: {fact.entity}\n"
        f"  attribute: {fact.attribute}\n"
        f"  fact_kind: {fact.fact_kind}\n"
        f"  value: {val.strip()}\n"
        f"  period: {fact.period.get('raw_label') or '(none)'}\n"
        f"  qualifiers: {quals}\n"
        f"  evidence: {_fence_evidence(evidence)}"
    )


def build_prompt(
    a: ComparableFact, evidence_a: str, b: ComparableFact, evidence_b: str, extra: str = ""
) -> str:
    prompt = f"{_render('A', a, evidence_a)}\n\n{_render('B', b, evidence_b)}"
    if extra:
        prompt += f"\n\nADDITIONAL CONTEXT GATHERED\n{extra}"
    return prompt


async def adjudicate_pair(
    a: ComparableFact,
    evidence_a: str,
    b: ComparableFact,
    evidence_b: str,
    provider: LLMProvider,
    *,
    extra_context: str = "",
    allow_more_context: bool = True,
) -> Adjudication:
    user = build_prompt(a, evidence_a, b, evidence_b, extra_context)
    if not allow_more_context:
        user += (
            "\n\nThis is the final decision. Classify with what is above; "
            "set needs_more_context false."
        )
    result = await provider.complete(
        CompletionRequest(
            system=SYSTEM_PROMPT,
            user=user,
            json_schema=_SCHEMA,
            temperature=0.0,
        )
    )
    payload = result.json()
    if not isinstance(payload, dict):
        raise ProviderError(f"adjudicator returned a non-object: {payload!r:.200}")
    adj = Adjudication.from_payload(payload)
    if not allow_more_context and adj.needs_more_context:
        return Adjudication(
            relationship_type=adj.relationship_type,
            reconciliation_basis=adj.reconciliation_basis,
            explanation=adj.explanation,
            confidence=adj.confidence,
            needs_more_context=False,
            missing_context=None,
            reasoning=adj.reasoning,
        )
    return adj

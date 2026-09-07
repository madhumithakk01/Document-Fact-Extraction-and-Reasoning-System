"""Canonicalization adjudication (§6.4).

Decides whether two entity or attribute strings name the same concept. Exact
matches and clearly unrelated strings are settled without a model call; the
uncertain middle gets one small adjudication call that is told to prefer *not*
merging, because a false merge silently corrupts every comparison built on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.providers.base import CompletionRequest, LLMProvider, ProviderError

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {"the", "of", "a", "an", "and", "for", "to", "in", "on", "s", "total"}
# above this token overlap we still ask the model; below it we say "not the same"
_MIN_JACCARD_TO_ASK = 0.2

_SYSTEM = """\
You decide whether two short labels name the SAME underlying concept in a set of
documents. Prefer answering false: only say true when they are clearly the same
measure or entity written differently (an abbreviation, a reordering, a spelling
or spacing variant, a sub-word). Different scope, different metric, or a
parent/child relationship is NOT the same concept.

Return same_concept, a canonical_name (the clearer of the two labels, or a clean
merge of them) and one sentence of reasoning.\
"""

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "same_concept": {"type": "boolean"},
        "canonical_name": {"type": "string"},
        "reasoning": {"type": "string"},
    },
    "required": ["same_concept", "canonical_name", "reasoning"],
}


@dataclass(frozen=True, slots=True)
class ConceptDecision:
    same_concept: bool
    canonical_name: str
    reasoning: str
    method: str  # exact | disjoint | model | model_error


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _tokens(s: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(s.lower()) if t not in _STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


async def adjudicate_same_concept(
    a: str,
    b: str,
    kind: str,
    provider: LLMProvider,
) -> ConceptDecision:
    na, nb = _norm(a), _norm(b)
    if na == nb:
        return ConceptDecision(
            True, a.strip() or b.strip(), "identical after normalization", "exact"
        )

    ta, tb = _tokens(na), _tokens(nb)
    if ta == tb and ta:
        return ConceptDecision(
            True, min((a, b), key=len).strip(), "same tokens, reordered", "exact"
        )

    if _jaccard(ta, tb) < _MIN_JACCARD_TO_ASK and not (na in nb or nb in na):
        return ConceptDecision(False, a.strip(), "labels share almost no words", "disjoint")

    try:
        result = await provider.complete(
            CompletionRequest(
                system=_SYSTEM,
                user=f'kind: {kind}\nlabel A: "{a}"\nlabel B: "{b}"',
                json_schema=_SCHEMA,
                temperature=0.0,
            )
        )
        payload = result.json()
        if not isinstance(payload, dict):
            raise ProviderError("adjudicator returned a non-object")
        same = bool(payload.get("same_concept"))
        canonical = str(payload.get("canonical_name") or a).strip() or a.strip()
        return ConceptDecision(
            same_concept=same,
            canonical_name=canonical if same else a.strip(),
            reasoning=str(payload.get("reasoning") or ""),
            method="model",
        )
    except (ProviderError, ValueError) as exc:
        # cannot confirm -> do not merge
        return ConceptDecision(False, a.strip(), f"adjudicator unavailable: {exc}", "model_error")

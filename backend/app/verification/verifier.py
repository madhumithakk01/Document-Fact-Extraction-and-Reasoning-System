"""Per-fact verification: grounding -> independent check -> one bounded fix."""

from __future__ import annotations

import logging
import re

from pydantic import ValidationError

from app.extraction.schema import AnchoredFact, CandidateFact, Comparator
from app.ingestion.types import Chunk
from app.providers.base import CompletionRequest, LLMProvider, ProviderError
from app.verification.grounding import check_grounding
from app.verification.prompts import (
    INDEPENDENT_VERIFY_SCHEMA,
    INDEPENDENT_VERIFY_SYSTEM,
    build_verify_prompt,
)
from app.verification.schema import (
    FactVerification,
    IndependentVerdict,
    IndependentVerification,
    VerificationLogEntry,
    VerificationOutcome,
    VerificationStage,
    VerifierIssue,
)

logger = logging.getLogger(__name__)

_SUPPORTED_MIN_CONFIDENCE = 0.5
_CORRECTABLE_FIELDS = {
    "value.number",
    "value.number_high",
    "value.unit",
    "value.comparator",
    "value.state",
    "value.text",
    "entity",
    "attribute",
    "period",
    "period.raw_label",
}
_COMPARATOR_WORDS = {
    "greater than": Comparator.gt,
    "more than": Comparator.gt,
    "over": Comparator.gt,
    "at least": Comparator.gte,
    "less than": Comparator.lt,
    "under": Comparator.lt,
    "at most": Comparator.lte,
    "up to": Comparator.lte,
    "about": Comparator.approx,
    "approximately": Comparator.approx,
    "around": Comparator.approx,
    "exact": Comparator.eq,
    "exactly": Comparator.eq,
}
_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")
_CURRENCY_MARKS = " \t₹$€£"  # space, tab, ₹ $ € £


def _cited_span(fact: AnchoredFact) -> str:
    if fact.anchor is not None and fact.anchor.matched_text:
        return fact.anchor.matched_text
    return fact.candidate.evidence_text


def _in_accounting_parens(text: str, start: int, end: int) -> bool:
    """True when ``text[start:end]`` is bracketed as ``(1,234)`` in the
    accounting sense - only currency marks, a short currency word, or a short
    unit word may sit between the number and the surrounding parentheses."""
    i = start - 1
    while i >= 0 and text[i] in _CURRENCY_MARKS:
        i -= 1
    word_start = i
    while word_start >= 0 and text[word_start].isalpha():
        word_start -= 1
    if 0 < i - word_start <= 4:  # a currency word like "Rs" / "INR"
        i = word_start
        while i >= 0 and text[i] in " \t":
            i -= 1
    if i < 0 or text[i] != "(":
        return False

    n = len(text)
    k = end
    while k < n and text[k] in " \t%":
        k += 1
    word_end = k
    while word_end < n and (text[word_end].isalpha() or text[word_end] == "."):
        word_end += 1
    if 0 < word_end - k <= 8:  # a unit word like "crore" / "mn" / "cr."
        k = word_end
        while k < n and text[k] in " \t":
            k += 1
    return k < n and text[k] == ")"


def _parse_number(text: str) -> float | None:
    normalized = text.replace("−", "-")
    m = _NUMBER_RE.search(normalized)
    if not m:
        return None
    try:
        value = float(m.group(0).replace(",", ""))
    except ValueError:
        return None
    # accounting convention: a bare parenthesised figure is negative
    if value >= 0 and _in_accounting_parens(normalized, m.start(), m.end()):
        value = -value
    return value


def _parse_comparator(text: str) -> Comparator | None:
    t = text.strip().lower()
    try:
        return Comparator(t)
    except ValueError:
        pass
    for word, comp in _COMPARATOR_WORDS.items():
        if word in t:
            return comp
    return None


async def independent_verify(
    fact: CandidateFact,
    cited_span: str,
    provider: LLMProvider,
) -> IndependentVerification:
    request = CompletionRequest(
        system=INDEPENDENT_VERIFY_SYSTEM,
        user=build_verify_prompt(fact, cited_span),
        json_schema=INDEPENDENT_VERIFY_SCHEMA,
        temperature=0.0,
    )
    result = await provider.complete(request)
    payload = result.json()
    if not isinstance(payload, dict):
        raise ProviderError(f"verifier returned non-object: {payload!r:.200}")
    return IndependentVerification.model_validate(payload)


def apply_correction(
    fact: CandidateFact, issues: list[VerifierIssue]
) -> tuple[CandidateFact, str] | None:
    """Apply the first coercible suggested correction. One field only."""
    for issue in issues:
        field = issue.field.strip().lower()
        suggestion = (issue.suggested_correction or "").strip()
        if not suggestion or field not in _CORRECTABLE_FIELDS:
            continue

        patched = fact.model_copy(deep=True)
        if field == "value.number":
            n = _parse_number(suggestion)
            if n is None:
                continue
            patched.value.number = n
        elif field == "value.number_high":
            n = _parse_number(suggestion)
            if n is None:
                continue
            patched.value.number_high = n
        elif field == "value.unit":
            if len(suggestion) > 40:
                continue
            patched.value.unit = suggestion
        elif field == "value.comparator":
            comp = _parse_comparator(suggestion)
            if comp is None:
                continue
            patched.value.comparator = comp
        elif field == "value.state":
            patched.value.state = suggestion
        elif field == "value.text":
            patched.value.text = suggestion
        elif field == "entity":
            if len(suggestion) > 120:
                continue
            patched.entity = suggestion
        elif field == "attribute":
            if len(suggestion) > 120:
                continue
            patched.attribute = suggestion
        elif field in ("period", "period.raw_label"):
            if len(suggestion) > 60:
                continue
            patched.period.raw_label = suggestion
        else:  # pragma: no cover - guarded by _CORRECTABLE_FIELDS
            continue

        try:
            patched = CandidateFact.model_validate(patched.model_dump())
        except ValidationError:
            continue
        return patched, f"{field} -> {suggestion!r}"
    return None


async def verify_fact(
    anchored: AnchoredFact,
    chunk: Chunk | None,
    provider: LLMProvider,
) -> FactVerification:
    log: list[VerificationLogEntry] = []
    notes: list[str] = []

    # --- step 1: deterministic grounding ---
    chunk_text = chunk.text if chunk is not None else ""
    grounding = check_grounding(anchored.candidate.evidence_text, chunk_text)
    log.append(
        VerificationLogEntry(
            stage=VerificationStage.grounding_check,
            result="pass" if grounding.passed else "fail",
            issue=None if grounding.passed else grounding.reason,
        )
    )
    if not grounding.passed:
        return FactVerification(
            fact=anchored,
            final_status=VerificationOutcome.rejected,
            log=log,
            notes=[f"grounding failed: {grounding.reason}"],
        )

    span = _cited_span(anchored)

    # --- step 2: independent verification ---
    try:
        verification = await independent_verify(anchored.candidate, span, provider)
    except (ProviderError, ValidationError) as exc:
        logger.warning("independent verifier unavailable: %s", exc)
        log.append(
            VerificationLogEntry(
                stage=VerificationStage.independent_verify,
                result="error",
                issue=str(exc)[:300],
            )
        )
        return FactVerification(
            fact=anchored,
            final_status=VerificationOutcome.needs_review,
            log=log,
            notes=["independent verifier could not be reached; flagged for review"],
        )

    log.append(
        VerificationLogEntry(
            stage=VerificationStage.independent_verify,
            result=verification.verdict.value,
            issue="; ".join(f"{i.field}: {i.problem}" for i in verification.issues) or None,
            detail={"supported_confidence": verification.supported_confidence, "attempt": 1},
        )
    )

    if (
        verification.verdict is IndependentVerdict.supported
        and verification.supported_confidence >= _SUPPORTED_MIN_CONFIDENCE
    ):
        return FactVerification(
            fact=anchored,
            final_status=VerificationOutcome.verified,
            verifier_confidence=verification.supported_confidence,
            log=log,
            notes=notes,
        )

    # --- step 3: one bounded auto-correct + recheck ---
    correction = apply_correction(anchored.candidate, verification.issues)
    if correction is None:
        return FactVerification(
            fact=anchored,
            final_status=VerificationOutcome.needs_review,
            verifier_confidence=verification.supported_confidence,
            log=log,
            notes=[f"verifier: {verification.verdict.value}; no safe correction available"],
        )

    corrected_fact, change = correction
    try:
        recheck = await independent_verify(corrected_fact, span, provider)
    except (ProviderError, ValidationError) as exc:
        log.append(
            VerificationLogEntry(
                stage=VerificationStage.independent_verify,
                result="error",
                issue=f"recheck failed: {exc}"[:300],
                detail={"attempt": 2, "correction": change},
            )
        )
        return FactVerification(
            fact=anchored,
            final_status=VerificationOutcome.needs_review,
            verifier_confidence=verification.supported_confidence,
            log=log,
            notes=[f"attempted correction ({change}) but recheck failed"],
        )

    log.append(
        VerificationLogEntry(
            stage=VerificationStage.independent_verify,
            result=recheck.verdict.value,
            issue="; ".join(f"{i.field}: {i.problem}" for i in recheck.issues) or None,
            detail={
                "supported_confidence": recheck.supported_confidence,
                "attempt": 2,
                "correction": change,
            },
        )
    )

    if (
        recheck.verdict is IndependentVerdict.supported
        and recheck.supported_confidence >= _SUPPORTED_MIN_CONFIDENCE
    ):
        return FactVerification(
            fact=anchored,
            final_status=VerificationOutcome.auto_corrected,
            verifier_confidence=recheck.supported_confidence,
            corrected=True,
            corrected_fact=corrected_fact,
            log=log,
            notes=[f"auto-corrected: {change}"],
        )

    return FactVerification(
        fact=anchored,
        final_status=VerificationOutcome.needs_review,
        verifier_confidence=recheck.supported_confidence,
        log=log,
        notes=[f"correction ({change}) did not resolve the discrepancy"],
    )

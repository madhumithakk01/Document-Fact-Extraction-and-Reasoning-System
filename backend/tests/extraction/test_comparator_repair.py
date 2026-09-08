from __future__ import annotations

import pytest

from app.extraction.extractor import repair_comparator
from app.extraction.schema import CandidateFact, Comparator


def quant(evidence: str, comparator: str | None) -> CandidateFact:
    return CandidateFact.model_validate(
        {
            "fact_kind": "quantitative",
            "entity": "Acme",
            "attribute": "shipments",
            "evidence_text": evidence,
            "value": {"comparator": comparator, "number": 33250.0, "unit": "units"},
        }
    )


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("delivered over 33,250 shipments", Comparator.gt),
        ("more than 33,250 shipments", Comparator.gt),
        ("at least 33,250 shipments", Comparator.gte),
        ("up to 33,250 shipments", Comparator.lte),
        ("fewer than 33,250 shipments", Comparator.lt),
        ("approximately 33,250 shipments", Comparator.approx),
        ("~33,250 shipments", Comparator.approx),
    ],
)
def test_approximate_language_overrides_eq(phrase: str, expected: Comparator) -> None:
    fact = quant(phrase, "eq")
    assert repair_comparator(fact) is True
    assert fact.value.comparator is expected


def test_exact_figure_stays_eq() -> None:
    fact = quant("reported 33,250 shipments in the quarter", "eq")
    assert repair_comparator(fact) is False
    assert fact.value.comparator is Comparator.eq


def test_missing_comparator_defaults_to_eq_without_approx_language() -> None:
    fact = quant("reported 33,250 shipments", None)
    repair_comparator(fact)
    assert fact.value.comparator is Comparator.eq


@pytest.mark.parametrize(
    "evidence",
    [
        "delivered 33,250 shipments, up from more than 30,000 a year earlier",
        "delivered 33,250 shipments (management had guided to over 30,000)",
        "shipments were 33,250 this quarter; over 40,000 are expected next quarter",
        "33,250 shipments versus approximately 30,000 in the prior period",
    ],
)
def test_keyword_in_a_neighbouring_clause_does_not_flip_the_exact_figure(evidence: str) -> None:
    fact = quant(evidence, "eq")
    assert repair_comparator(fact) is False
    assert fact.value.comparator is Comparator.eq


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        ("revenue of over 33,250 crore, up from 30,000 crore last year", Comparator.gt),
        ("handled approximately 33,250 shipments, in line with guidance", Comparator.approx),
    ],
)
def test_keyword_in_the_number_s_own_clause_still_repairs(
    evidence: str, expected: Comparator
) -> None:
    fact = quant(evidence, "eq")
    assert repair_comparator(fact) is True
    assert fact.value.comparator is expected


def test_model_supplied_inequality_is_not_overridden() -> None:
    fact = quant("about 33,250 shipments", "gte")
    assert repair_comparator(fact) is False
    assert fact.value.comparator is Comparator.gte


def test_non_quantitative_untouched() -> None:
    fact = CandidateFact.model_validate(
        {
            "fact_kind": "status",
            "entity": "Acme",
            "attribute": "profitability",
            "evidence_text": "the group turned profitable, well over expectations",
            "value": {"state": "profitable"},
        }
    )
    assert repair_comparator(fact) is False

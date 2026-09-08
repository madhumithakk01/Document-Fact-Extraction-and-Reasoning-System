from __future__ import annotations

import pytest

from app.extraction.schema import CandidateFact, Comparator
from app.verification.schema import VerifierIssue
from app.verification.verifier import _parse_number, apply_correction


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("(1,234)", -1234.0),
        ("(1,234.50)", -1234.5),
        ("₹(1,234)", -1234.0),
        ("Rs (1,234) cr", -1234.0),
        ("(1,234) crore", -1234.0),
        ("(1,234 crore)", -1234.0),
        ("(0)", 0.0),
        ("(4.5%)", -4.5),  # a parenthesised percentage is a decline
        # not the accounting convention -> unchanged
        ("1,234", 1234.0),
        ("-1,234", -1234.0),
        ("(-1,234)", -1234.0),
        ("revenue rose 5%", 5.0),
        ("EBITDA of 127 (see note 4)", 127.0),
        ("net loss narrowed", None),
    ],
)
def test_parse_number_handles_parenthesised_negatives(text: str, expected: float | None) -> None:
    assert _parse_number(text) == expected


def fact(**value: object) -> CandidateFact:
    return CandidateFact.model_validate(
        {
            "fact_kind": "quantitative",
            "entity": "Delhivery",
            "attribute": "FY24 consolidated EBITDA",
            "evidence_text": "FY24 consolidated EBITDA was INR 1,266.41 million",
            "value": {"comparator": "eq", "number": 127.0, "unit": "INR Crore", **value},
            "period": {"raw_label": "FY24"},
        }
    )


def _issues(*items: dict) -> list[VerifierIssue]:
    return [VerifierIssue.model_validate(i) for i in items]


def test_number_correction_parses_grouped_number() -> None:
    out = apply_correction(
        fact(),
        _issues(
            {"field": "value.number", "problem": "wrong scale", "suggested_correction": "1,266.41"}
        ),
    )
    assert out is not None
    patched, change = out
    assert patched.value.number == 1266.41
    assert "value.number" in change


def test_number_correction_reads_parenthesised_figure_as_negative() -> None:
    out = apply_correction(
        fact(),
        _issues(
            {
                "field": "value.number",
                "problem": "figure is a loss, shown in parentheses",
                "suggested_correction": "(1,234)",
            }
        ),
    )
    assert out is not None
    assert out[0].value.number == -1234.0


def test_unit_correction_applied() -> None:
    out = apply_correction(
        fact(),
        _issues(
            {
                "field": "value.unit",
                "problem": "unit mismatch",
                "suggested_correction": "INR million",
            }
        ),
    )
    assert out is not None and out[0].value.unit == "INR million"


def test_comparator_word_maps_to_enum() -> None:
    out = apply_correction(
        fact(comparator="eq"),
        _issues(
            {
                "field": "value.comparator",
                "problem": "should be an inequality",
                "suggested_correction": "more than",
            }
        ),
    )
    assert out is not None and out[0].value.comparator is Comparator.gt


def test_first_coercible_issue_wins_and_noncoercible_skipped() -> None:
    out = apply_correction(
        fact(),
        _issues(
            {"field": "evidence_text", "problem": "not correctable", "suggested_correction": "x"},
            {"field": "fact_kind", "problem": "not correctable", "suggested_correction": "status"},
            {"field": "value.unit", "problem": "unit", "suggested_correction": "INR million"},
        ),
    )
    assert out is not None and out[0].value.unit == "INR million"


def test_returns_none_when_no_coercible_correction() -> None:
    assert (
        apply_correction(
            fact(),
            _issues({"field": "entity", "problem": "unclear", "suggested_correction": None}),
        )
        is None
    )


def test_overly_long_entity_correction_rejected() -> None:
    assert (
        apply_correction(
            fact(),
            _issues({"field": "entity", "problem": "x", "suggested_correction": "y" * 200}),
        )
        is None
    )


def test_unparseable_number_correction_rejected() -> None:
    assert (
        apply_correction(
            fact(),
            _issues({"field": "value.number", "problem": "x", "suggested_correction": "a lot"}),
        )
        is None
    )

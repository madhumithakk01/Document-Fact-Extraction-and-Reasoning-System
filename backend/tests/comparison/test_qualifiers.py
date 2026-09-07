from __future__ import annotations

from app.comparison.qualifiers import (
    differing_significant_qualifiers,
    significant_qualifiers,
)


def test_maps_raw_keys_onto_canonical_significant_ones() -> None:
    sig = significant_qualifiers(
        {"consolidated_vs_standalone": "Consolidated", "Currency": "INR", "colour": "blue"}
    )
    # values are normalized for comparison (case-folded)
    assert sig == {"consolidation": "consolidated", "currency": "inr"}


def test_value_synonyms_are_normalized() -> None:
    assert significant_qualifiers({"audited": "Unaudited"})["audited"] == "unaudited"
    assert significant_qualifiers({"forecast_vs_actual": "projected"})["forecast_vs_actual"] == (
        "forecast"
    )


def test_difference_requires_both_sides_to_state_it() -> None:
    a = {"basis": "gross"}
    b = {"currency": "INR"}
    assert differing_significant_qualifiers(a, b) == []


def test_flags_a_real_disagreement() -> None:
    a = {"consolidation": "consolidated", "currency": "INR"}
    b = {"consolidation": "standalone", "currency": "INR"}
    assert differing_significant_qualifiers(a, b) == ["consolidation"]


def test_agreeing_qualifiers_are_not_flagged() -> None:
    a = {"basis": "gross", "currency": "INR"}
    b = {"basis": "gross", "currency": "INR"}
    assert differing_significant_qualifiers(a, b) == []

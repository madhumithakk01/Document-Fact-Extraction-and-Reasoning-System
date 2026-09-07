from __future__ import annotations

import pytest

from app.comparison.precheck import ComparableFact, PrecheckOutcome, deterministic_precheck


def q(number, unit="INR Crore", comparator="eq", period="FY24", qualifiers=None, **over):
    return ComparableFact(
        fact_kind="quantitative",
        entity=over.get("entity", "Delhivery"),
        attribute=over.get("attribute", "FY24 consolidated EBITDA"),
        value={"comparator": comparator, "number": number, "unit": unit},
        period={"raw_label": period},
        qualifiers=qualifiers or {},
        canonical_entity=over.get("canonical_entity"),
        canonical_attribute=over.get("canonical_attribute"),
    )


def test_the_over_33250_case_resolves_with_zero_model_calls() -> None:
    a = q(33250, unit="shipments", comparator="gt", attribute="express parcel shipments")
    b = q(33278, unit="shipments", comparator="eq", attribute="express parcel shipments")
    result = deterministic_precheck(a, b)
    assert result.outcome is PrecheckOutcome.corroborates


def test_same_figure_different_units_corroborates() -> None:
    a = q(127, unit="INR Crore")
    b = q(1266.41, unit="INR million", period="FY 2023-24")
    assert deterministic_precheck(a, b).outcome is PrecheckOutcome.corroborates


def test_close_but_distinct_point_estimates_go_to_adjudication() -> None:
    a = q(6.5, unit="%", attribute="real GDP growth", period="2025-26")
    b = q(6.6, unit="%", attribute="real GDP growth", period="2025-26")
    assert deterministic_precheck(a, b).outcome is PrecheckOutcome.needs_adjudication


def test_differing_significant_qualifier_is_not_auto_resolved() -> None:
    a = q(100, qualifiers={"basis": "consolidated"})
    b = q(100, qualifiers={"basis": "standalone"})
    r = deterministic_precheck(a, b)
    assert r.outcome is PrecheckOutcome.needs_adjudication
    assert "basis" in r.reason


def test_different_currencies_need_adjudication() -> None:
    assert (
        deterministic_precheck(q(100, unit="INR Cr"), q(100, unit="USD mn")).outcome
        is PrecheckOutcome.needs_adjudication
    )


def test_incompatible_dimensions_are_not_comparable() -> None:
    assert (
        deterministic_precheck(q(6.5, unit="%"), q(6.5, unit="INR Cr")).outcome
        is PrecheckOutcome.not_comparable
    )


def test_disjoint_periods_are_not_comparable() -> None:
    assert (
        deterministic_precheck(q(100, period="FY24"), q(100, period="FY23")).outcome
        is PrecheckOutcome.not_comparable
    )


def test_overlapping_but_unequal_periods_need_adjudication() -> None:
    assert (
        deterministic_precheck(q(100, period="Q4 FY24"), q(100, period="FY24")).outcome
        is PrecheckOutcome.needs_adjudication
    )


def test_different_fact_kinds_are_not_comparable() -> None:
    a = q(100)
    b = ComparableFact(
        "status",
        "Delhivery",
        "FY24 consolidated EBITDA",
        {"state": "profitable"},
        {"raw_label": "FY24"},
    )
    assert deterministic_precheck(a, b).outcome is PrecheckOutcome.not_comparable


def test_different_entities_are_not_comparable() -> None:
    assert (
        deterministic_precheck(q(100, entity="Delhivery"), q(100, entity="Blue Dart")).outcome
        is PrecheckOutcome.not_comparable
    )


def test_canonical_names_override_raw_strings() -> None:
    a = q(127, attribute="EBITDA", canonical_attribute="consolidated ebitda")
    b = q(
        1266.41,
        unit="INR million",
        attribute="operating EBITDA",
        canonical_attribute="consolidated ebitda",
        period="FY 2023-24",
    )
    assert deterministic_precheck(a, b).outcome is PrecheckOutcome.corroborates


def test_status_facts_same_state_corroborate() -> None:
    a = ComparableFact(
        "status", "Delhivery", "PAT", {"state": "Profitable"}, {"raw_label": "Q3 FY24"}
    )
    b = ComparableFact(
        "status", "Delhivery", "PAT", {"state": "profitable"}, {"raw_label": "Q3 FY24"}
    )
    assert deterministic_precheck(a, b).outcome is PrecheckOutcome.corroborates


def test_status_facts_different_state_need_adjudication() -> None:
    a = ComparableFact("status", "X", "listing", {"state": "listed"}, {"raw_label": "FY24"})
    b = ComparableFact("status", "X", "listing", {"state": "delisted"}, {"raw_label": "FY24"})
    assert deterministic_precheck(a, b).outcome is PrecheckOutcome.needs_adjudication


def test_qualitative_facts_always_need_adjudication() -> None:
    a = ComparableFact(
        "qualitative", "SCS", "ebitda", {"text": "doubled over FY23"}, {"raw_label": "FY24"}
    )
    b = ComparableFact(
        "qualitative", "SCS", "ebitda", {"text": "improved significantly"}, {"raw_label": "FY24"}
    )
    assert deterministic_precheck(a, b).outcome is PrecheckOutcome.needs_adjudication


@pytest.mark.parametrize(
    ("comparator", "other"),
    [("gt", 50), ("gte", 50), ("lt", 900), ("approx", 500), ("eq", 500)],
)
def test_precheck_defers_genuine_disagreement_never_declares_it(comparator, other) -> None:
    """Deterministic resolves corroboration only; a disagreement always defers to
    adjudication and is never called a contradiction here."""
    a = q(100, comparator=comparator)
    b = q(other, comparator="eq")
    result = deterministic_precheck(a, b)
    assert result.outcome is PrecheckOutcome.needs_adjudication

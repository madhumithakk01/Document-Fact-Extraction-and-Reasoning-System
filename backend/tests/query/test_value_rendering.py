"""A quantitative value with no asserted comparator must not render as exact."""

from __future__ import annotations

from types import SimpleNamespace

from app.query.tools import format_quantitative_value, summarize_fact


def _qfact(value: dict) -> SimpleNamespace:
    return SimpleNamespace(
        fact_kind="quantitative",
        value=value,
        entity="Acme",
        attribute="revenue",
        period={"raw_label": "FY24"},
        page_number=1,
        verification_status="verified",
    )


def test_missing_comparator_is_marked_approximate_not_exact() -> None:
    rendered = format_quantitative_value({"number": 127, "unit": "crore"})
    assert rendered == "~127 crore"
    assert "eq" not in rendered


def test_none_comparator_is_treated_as_unspecified() -> None:
    assert format_quantitative_value({"comparator": None, "number": 5, "unit": ""}) == "~5"


def test_explicit_eq_renders_clean_without_a_prefix() -> None:
    assert (
        format_quantitative_value({"comparator": "eq", "number": 127, "unit": "crore"})
        == "127 crore"
    )


def test_inequality_comparator_is_preserved() -> None:
    assert (
        format_quantitative_value({"comparator": "over", "number": 40, "unit": "hubs"})
        == "over 40 hubs"
    )


def test_summarize_fact_uses_the_honest_renderer() -> None:
    line = summarize_fact(_qfact({"number": 8142, "unit": "crore"}))
    assert "= ~8142 crore" in line
    assert " eq " not in line

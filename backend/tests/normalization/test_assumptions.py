"""Silent-assumption detection and its confidence penalty."""

from __future__ import annotations

import pytest

from app.normalization.assumptions import (
    CONFIDENCE_FLOOR,
    detect_assumptions,
    penalize_confidence,
)


def _detect(**overrides) -> list[str]:
    kwargs = {
        "fact_kind": "quantitative",
        "entity_resolved": True,
        "value": {"comparator": "eq", "number": 1},
        "period_label": "calendar year 2024",
    }
    kwargs.update(overrides)
    return detect_assumptions(**kwargs)


def test_clean_fact_has_no_assumptions() -> None:
    assert _detect() == []


def test_undated_fiscal_year_flags_the_convention() -> None:
    assert _detect(period_label="FY24") == ["fy_convention_assumed"]
    assert _detect(period_label="Q3 FY24") == ["fy_convention_assumed"]
    assert _detect(period_label="H1 FY24") == ["fy_convention_assumed"]


def test_bare_calendar_year_does_not_flag_a_fiscal_convention() -> None:
    # "2024" parses with the default FY month too, but a calendar year does not
    # depend on it, so it must not be reported as an assumption.
    assert _detect(period_label="2024") == []
    assert _detect(period_label="calendar year 2024") == []


def test_plain_date_label_is_not_a_fiscal_assumption() -> None:
    assert _detect(period_label="March 31, 2024") == []
    assert _detect(period_label="") == []


def test_inferred_entity_is_flagged() -> None:
    assert _detect(entity_resolved=False) == ["entity_inferred"]


def test_missing_comparator_is_flagged_only_for_quantitative() -> None:
    assert _detect(value={"number": 1}) == ["comparator_unspecified"]
    assert _detect(value={"comparator": None, "number": 1}) == ["comparator_unspecified"]
    assert _detect(fact_kind="status", value={"state": "profitable"}) == []


def test_flags_accumulate_in_a_stable_order() -> None:
    flags = _detect(entity_resolved=False, value={"number": 1}, period_label="FY24")
    assert flags == ["entity_inferred", "comparator_unspecified", "fy_convention_assumed"]


def test_penalty_is_ten_points_per_flag() -> None:
    assert penalize_confidence(0.9, []) == pytest.approx(0.9)
    assert penalize_confidence(0.9, ["a"]) == pytest.approx(0.8)
    assert penalize_confidence(0.9, ["a", "b", "c"]) == pytest.approx(0.6)


def test_penalty_never_drops_below_the_floor() -> None:
    assert penalize_confidence(0.1, ["a", "b", "c"]) == CONFIDENCE_FLOOR

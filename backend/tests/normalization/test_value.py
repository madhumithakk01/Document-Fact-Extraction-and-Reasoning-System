from __future__ import annotations

from app.normalization.units import Dimension
from app.normalization.value import normalize_value


def test_scales_interval_onto_base_unit() -> None:
    nv = normalize_value("quantitative", {"comparator": "eq", "number": 127, "unit": "INR Crore"})
    assert nv.dimension is Dimension.currency
    assert nv.currency == "INR"
    assert nv.interval.low <= 1.27e9 <= nv.interval.high


def test_crore_and_million_land_on_the_same_scale() -> None:
    a = normalize_value("quantitative", {"comparator": "eq", "number": 127, "unit": "INR Crore"})
    b = normalize_value(
        "quantitative", {"comparator": "eq", "number": 1266.41, "unit": "INR million"}
    )
    assert a.interval.overlaps(b.interval)


def test_over_comparator_produces_open_ray() -> None:
    nv = normalize_value("quantitative", {"comparator": "gt", "number": 33250, "unit": "shipments"})
    assert nv.interval.contains_point(33251)
    assert not nv.interval.contains_point(33250)


def test_status_value_is_normalized_text() -> None:
    nv = normalize_value("status", {"state": "  Profitable  "})
    assert nv.kind == "status"
    assert nv.state == "profitable"
    assert nv.interval is None


def test_qualitative_value_keeps_text() -> None:
    nv = normalize_value("qualitative", {"text": "doubled over FY23"})
    assert nv.kind == "qualitative"
    assert nv.text == "doubled over FY23"


def test_missing_number_is_not_comparable() -> None:
    nv = normalize_value("quantitative", {"comparator": "eq", "unit": "INR Crore"})
    assert not nv.comparable

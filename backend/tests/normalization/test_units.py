from __future__ import annotations

import math

import pytest

from app.normalization.units import Dimension, parse_quantity


@pytest.mark.parametrize(
    ("number", "unit", "expected_magnitude", "expected_dim", "expected_ccy"),
    [
        (127, "INR Crore", 1.27e9, Dimension.currency, "INR"),
        (1266.41, "INR million", 1.26641e9, Dimension.currency, "INR"),
        (5, "Rs. Lakh", 5e5, Dimension.currency, "INR"),
        (3.2, "INR lakh crore", 3.2e5 * 1e7, Dimension.currency, "INR"),
        (45, "thousand crore", 45 * 1e3 * 1e7, Dimension.count, None),
        (2.8, "billion", 2.8e9, Dimension.count, None),
        (740, "Mn", 7.4e8, Dimension.count, None),
        (33, "k", 33_000, Dimension.count, None),
        (6.5, "%", 0.065, Dimension.percent, None),
        (50, "bps", 0.005, Dimension.percent, None),
        (1.4, "Mn Tonnes", 1.4e6 * 1e3, Dimension.mass, None),
        (500, "km", 500_000, Dimension.length, None),
        (31, "days", 31, Dimension.duration, None),
        (12, "trucks", 12, Dimension.count, None),
    ],
)
def test_parse_quantity(number, unit, expected_magnitude, expected_dim, expected_ccy) -> None:
    q = parse_quantity(number, unit)
    assert math.isclose(q.magnitude, expected_magnitude, rel_tol=1e-9)
    assert q.dimension is expected_dim
    assert q.currency == expected_ccy


@pytest.mark.parametrize(
    ("number", "unit", "expected_m2"),
    [
        (1000, "sq ft", 1000 * 0.09290304),
        (1000, "square feet", 1000 * 0.09290304),
        (1000, "sq. ft.", 1000 * 0.09290304),
        (1000, "sqft", 1000 * 0.09290304),
        (1000, "ft2", 1000 * 0.09290304),
        (2.5, "million sq ft", 2.5e6 * 0.09290304),
        (1, "sq m", 1.0),
        (1, "m2", 1.0),
        (1, "sq km", 1e6),
        (1, "hectare", 10_000.0),
        (1, "ha", 10_000.0),
        (1, "acre", 4046.8564224),
        (1, "sq mi", 2_589_988.110336),
    ],
)
def test_area_units_normalize_to_square_metres(number, unit, expected_m2) -> None:
    q = parse_quantity(number, unit)
    assert q.dimension is Dimension.area
    assert math.isclose(q.magnitude, expected_m2, rel_tol=1e-9)


def test_linear_length_is_not_read_as_area() -> None:
    assert parse_quantity(1000, "ft").dimension is Dimension.length
    assert parse_quantity(500, "km").dimension is Dimension.length


def test_area_and_length_are_not_comparable_dimensions() -> None:
    # regression: "sq ft" used to parse as linear length in metres
    assert parse_quantity(100, "sq ft").dimension is not parse_quantity(100, "ft").dimension


def test_rupee_symbol_and_scale_together() -> None:
    q = parse_quantity(1266.41, "₹1,266.41 million")
    assert q.currency == "INR"
    assert math.isclose(q.magnitude, 1.26641e9)
    assert q.scale_word == "million"


def test_bare_number_has_unknown_dimension() -> None:
    q = parse_quantity(42, None)
    assert q.dimension is Dimension.unknown
    assert q.magnitude == 42


def test_dollar_per_kg_stays_currency() -> None:
    q = parse_quantity(3, "$/kg")
    assert q.dimension is Dimension.currency
    assert q.currency == "USD"

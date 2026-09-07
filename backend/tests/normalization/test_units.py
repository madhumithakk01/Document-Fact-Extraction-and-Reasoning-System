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

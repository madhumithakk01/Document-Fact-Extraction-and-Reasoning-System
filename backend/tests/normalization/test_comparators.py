from __future__ import annotations

import math

import pytest

from app.extraction.schema import Comparator
from app.normalization.comparators import (
    Interval,
    parse_comparator_phrase,
    value_interval,
)


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("delivered over 33,250 shipments", Comparator.gt),
        ("more than 5 crore", Comparator.gt),
        ("at least 100", Comparator.gte),
        ("up to 200", Comparator.lte),
        ("no more than 50", Comparator.lte),
        ("fewer than 10", Comparator.lt),
        ("approximately 6.5%", Comparator.approx),
        ("~33,250", Comparator.approx),
        ("between 5 and 7", Comparator.range),
        ("revenue was 8,142 crore", None),
    ],
)
def test_parse_comparator_phrase(phrase, expected) -> None:
    assert parse_comparator_phrase(phrase) is expected


def test_gt_is_an_open_ray() -> None:
    iv = value_interval(Comparator.gt, 33250)
    assert iv.low == 33250 and not iv.low_closed
    assert iv.high == math.inf
    assert iv.contains_point(33251)
    assert not iv.contains_point(33250)


def test_eq_is_the_half_open_rounding_bracket() -> None:
    iv = value_interval(Comparator.eq, 6.5)
    assert math.isclose(iv.low, 6.45) and iv.low_closed
    assert math.isclose(iv.high, 6.55) and not iv.high_closed


def test_adjacent_rounded_values_do_not_overlap() -> None:
    a = value_interval(Comparator.eq, 6.5)
    b = value_interval(Comparator.eq, 6.6)
    assert not a.overlaps(b)


def test_equal_values_overlap() -> None:
    assert value_interval(Comparator.eq, 127).overlaps(value_interval(Comparator.eq, 127))


def test_approx_band_is_relative() -> None:
    iv = value_interval(Comparator.approx, 100)
    assert iv.low <= 95 and iv.high >= 105


def test_range_spans_both_ends() -> None:
    iv = value_interval(Comparator.range, 5, 7)
    assert iv.contains_point(5) and iv.contains_point(6.9)


def test_rounding_precision_from_written_form() -> None:
    assert value_interval(Comparator.eq, 33278).overlaps(Interval(33277.6, 33277.6))
    # a trailing-zero integer implies coarser precision
    coarse = value_interval(Comparator.eq, 8100)
    assert coarse.low <= 8050 and coarse.high >= 8150


def test_no_number_returns_none() -> None:
    assert value_interval(Comparator.eq, None, None) is None

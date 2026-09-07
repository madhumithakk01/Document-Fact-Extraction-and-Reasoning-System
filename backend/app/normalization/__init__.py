"""Deterministic normalization.

Turns the free-text pieces of a fact -- a value with a scale word and currency,
a period label, a comparator -- into canonical, comparable forms with no model
call:

* :func:`parse_quantity` -> a magnitude on a base unit plus its dimension;
* :func:`parse_period` -> concrete start/end dates for fiscal-year, quarter,
  and calendar labels;
* :func:`value_interval` -> the closed/open interval of values a claim allows,
  accounting for the comparator and rounding precision.

These are the pieces the deterministic comparison pre-check runs on.
"""

from app.normalization.comparators import (
    Interval,
    parse_comparator_phrase,
    value_interval,
)
from app.normalization.dates import NormalizedPeriod, parse_period, periods_relation
from app.normalization.units import (
    Dimension,
    NormalizedQuantity,
    parse_quantity,
)
from app.normalization.value import NormalizedValue, normalize_value

__all__ = [
    "Dimension",
    "Interval",
    "NormalizedPeriod",
    "NormalizedQuantity",
    "NormalizedValue",
    "normalize_value",
    "parse_comparator_phrase",
    "parse_period",
    "parse_quantity",
    "periods_relation",
    "value_interval",
]

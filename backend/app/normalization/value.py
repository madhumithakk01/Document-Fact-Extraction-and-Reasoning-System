"""Combine unit and comparator normalization into one comparable value."""

from __future__ import annotations

from dataclasses import dataclass

from app.extraction.schema import Comparator
from app.normalization.comparators import Interval, value_interval
from app.normalization.units import Dimension, parse_quantity


@dataclass(frozen=True, slots=True)
class NormalizedValue:
    kind: str  # quantitative | status | qualitative
    dimension: Dimension = Dimension.unknown
    currency: str | None = None
    interval: Interval | None = None  # on the dimension's base unit
    state: str | None = None
    text: str | None = None
    scale_word: str | None = None

    @property
    def comparable(self) -> bool:
        return self.interval is not None and not self.interval.empty


def _norm_state(s: str) -> str:
    return " ".join(s.strip().lower().split())


def normalize_value(fact_kind: str, value: dict) -> NormalizedValue:
    if fact_kind == "status":
        return NormalizedValue(kind="status", state=_norm_state(value.get("state") or ""))
    if fact_kind == "qualitative":
        return NormalizedValue(kind="qualitative", text=(value.get("text") or "").strip())

    number = value.get("number")
    number_high = value.get("number_high")
    unit = value.get("unit")
    comparator_raw = value.get("comparator")
    comparator = None
    if isinstance(comparator_raw, Comparator):
        comparator = comparator_raw
    elif isinstance(comparator_raw, str):
        try:
            comparator = Comparator(comparator_raw)
        except ValueError:
            comparator = None

    if number is None and number_high is None:
        return NormalizedValue(kind="quantitative")

    base = number if number is not None else number_high
    q = parse_quantity(float(base), unit)

    # scale the interval endpoints from "as written" units onto the base unit
    factor = (q.magnitude / base) if base not in (0, None) else 1.0
    raw_interval = value_interval(comparator, number, number_high)
    interval = None
    if raw_interval is not None:
        interval = Interval(
            low=_scale(raw_interval.low, factor),
            high=_scale(raw_interval.high, factor),
            low_closed=raw_interval.low_closed,
            high_closed=raw_interval.high_closed,
        )
        if factor < 0:  # never happens for these units, but keep ordering sane
            interval = Interval(
                interval.high, interval.low, interval.high_closed, interval.low_closed
            )

    return NormalizedValue(
        kind="quantitative",
        dimension=q.dimension,
        currency=q.currency,
        interval=interval,
        scale_word=q.scale_word,
    )


def _scale(x: float, factor: float) -> float:
    if x == float("inf"):
        return float("inf")
    if x == float("-inf"):
        return float("-inf")
    return x * factor

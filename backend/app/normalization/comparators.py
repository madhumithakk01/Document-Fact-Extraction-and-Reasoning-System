"""Comparator semantics as value intervals.

A quantitative claim describes a *set* of values, not one point: "over 33,250"
is the open ray (33250, inf); "approximately 6.5%" is a band around 6.5;
"33,278" alone is [33277.5, 33278.5] once rounding precision is taken into
account. Two claims corroborate when their intervals overlap.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from app.extraction.schema import Comparator

_APPROX_REL_TOLERANCE = 0.05  # 5% band for "approximately"
_APPROX_MIN_TOLERANCE = 0.5

_PHRASE_TO_COMPARATOR: list[tuple[re.Pattern[str], Comparator]] = [
    (re.compile(r"\bno more than\b|\bnot more than\b|\bat most\b|\bup to\b", re.I), Comparator.lte),
    (re.compile(r"\bno less than\b|\bat least\b|\bminimum of\b|\bor more\b", re.I), Comparator.gte),
    (
        re.compile(
            r"\bmore than\b|\bgreater than\b|\bover\b|\bexceed(?:s|ed|ing)?\b"
            r"|\babove\b|\bnorth of\b|\+\s*$",
            re.I,
        ),
        Comparator.gt,
    ),
    (
        re.compile(r"\bless than\b|\bfewer than\b|\bunder\b|\bbelow\b|\bshy of\b", re.I),
        Comparator.lt,
    ),
    (
        re.compile(
            r"\bapprox(?:\.|imately)?\b|\babout\b|\baround\b|\broughly\b|\bnearly\b|\bcirca\b|~",
            re.I,
        ),
        Comparator.approx,
    ),
    (re.compile(r"\bbetween\b|\bfrom\b.*\bto\b|\brange of\b|[-–]\s*\d", re.I), Comparator.range),
]


def parse_comparator_phrase(text: str) -> Comparator | None:
    for pattern, comparator in _PHRASE_TO_COMPARATOR:
        if pattern.search(text):
            return comparator
    return None


@dataclass(frozen=True, slots=True)
class Interval:
    low: float
    high: float
    low_closed: bool = True
    high_closed: bool = True

    @property
    def empty(self) -> bool:
        if self.low > self.high:
            return True
        return self.low == self.high and not (self.low_closed and self.high_closed)

    def overlaps(self, other: Interval) -> bool:
        if self.empty or other.empty:
            return False
        if self.high < other.low or other.high < self.low:
            return False
        touch_high = self.high == other.low and not (self.high_closed and other.low_closed)
        touch_low = other.high == self.low and not (other.high_closed and self.low_closed)
        return not (touch_high or touch_low)

    def contains_point(self, x: float) -> bool:
        return self.overlaps(Interval(x, x))


def _rounding_half_step(number: float) -> float:
    """Half of the least significant place value of ``number`` as written.

    ``6.5`` -> 0.05, ``33278`` -> 0.5, ``8100`` -> 50 (trailing zeros read as
    coarser precision). A float that is really an integer (``8100.0``) is
    treated as the integer.
    """
    if number == 0:
        return 0.5
    text = repr(abs(number))
    if "e" in text or "E" in text:
        exp = math.floor(math.log10(abs(number)))
        return 0.5 * 10 ** (exp - 5)
    whole, _, frac = text.partition(".")
    frac = frac.rstrip("0")
    if frac:
        return 0.5 * 10 ** (-len(frac))
    trailing_zeros = len(whole) - len(whole.rstrip("0"))
    return 0.5 * 10**trailing_zeros


def value_interval(
    comparator: Comparator | None,
    number: float | None,
    number_high: float | None = None,
    *,
    approx_relative: float = _APPROX_REL_TOLERANCE,
) -> Interval | None:
    if number is None and number_high is None:
        return None
    n = number if number is not None else number_high
    assert n is not None
    half = _rounding_half_step(n)
    inf = math.inf

    if comparator is Comparator.gt:
        return Interval(n, inf, low_closed=False, high_closed=False)
    if comparator is Comparator.gte:
        return Interval(n, inf, low_closed=True, high_closed=False)
    if comparator is Comparator.lt:
        return Interval(-inf, n, low_closed=False, high_closed=False)
    if comparator is Comparator.lte:
        return Interval(-inf, n, low_closed=False, high_closed=True)
    if comparator is Comparator.approx:
        tol = max(abs(n) * approx_relative, _APPROX_MIN_TOLERANCE, half)
        return Interval(n - tol, n + tol)
    if comparator is Comparator.range:
        lo = number if number is not None else number_high
        hi = number_high if number_high is not None else number
        assert lo is not None and hi is not None
        if lo > hi:
            lo, hi = hi, lo
        return Interval(
            lo - _rounding_half_step(lo),
            hi + _rounding_half_step(hi),
            low_closed=True,
            high_closed=False,
        )
    # eq or unknown -> the half-open rounding bracket the written figure denotes:
    # "6.5" is [6.45, 6.55), so it does not touch "6.6" = [6.55, 6.65).
    return Interval(n - half, n + half, low_closed=True, high_closed=False)

"""Period-label parsing.

Resolves fiscal-year, quarter, half-year, calendar-year, and plain-date labels
to concrete ``start_date`` / ``end_date`` so two facts stated against differently
worded periods can be checked for the same span. The fiscal-year boundary month
defaults to April (the Indian convention); pass ``fy_start_month`` when the
document states its own.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

INDIA_FY_START_MONTH = 4


class PeriodKind(StrEnum):
    fiscal_year = "fiscal_year"
    quarter = "quarter"
    half = "half"
    calendar_year = "calendar_year"
    multi_year = "multi_year"
    date = "date"
    unknown = "unknown"


@dataclass(frozen=True, slots=True)
class NormalizedPeriod:
    raw_label: str
    kind: PeriodKind
    start_date: date | None
    end_date: date | None
    fy_start_month: int | None = None
    convention_assumed: bool = False

    @property
    def resolved(self) -> bool:
        return self.start_date is not None and self.end_date is not None


_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
_MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})

_FY_RE = re.compile(
    r"\b(?:fy|f\.y\.|fiscal(?:\s+year)?|financial\s+year)\s*"
    r"(?P<y1>\d{2,4})(?:\s*[-/–]\s*(?P<y2>\d{2,4}))?\b",
    re.I,
)
_BARE_SPAN_RE = re.compile(r"\b(?P<y1>\d{4})\s*[-/–]\s*(?P<y2>\d{2,4})\b")

# A period stated as two fiscal/calendar years joined by a word ("FY2019 to
# FY2024", "between CY2019 and CY2024", "from 2019 through 2024"). Distinct from
# a single fiscal-year label like "FY 2023-24": that is a dash-joined pair of
# consecutive years and is handled by _FY_RE / _BARE_SPAN_RE below.
_PERIOD_PREFIX = r"(?:fy|f\.y\.|fiscal(?:\s+year)?|financial\s+year|cy|calendar\s+year)"
_MULTI_YEAR_RES = (
    re.compile(
        rf"\bfrom\s+({_PERIOD_PREFIX}\s*)?(\d{{2,4}})\s*"
        rf"(?:to|through|thru|till|until|[-–—])\s*"
        rf"({_PERIOD_PREFIX}\s*)?(\d{{2,4}})\b",
        re.I,
    ),
    re.compile(
        rf"\bbetween\s+({_PERIOD_PREFIX}\s*)?(\d{{2,4}})\s*and\s+"
        rf"({_PERIOD_PREFIX}\s*)?(\d{{2,4}})\b",
        re.I,
    ),
    re.compile(
        rf"\b({_PERIOD_PREFIX})\s*(\d{{2,4}})\s*"
        rf"(?:to|through|thru|till|until|and|[-–—])\s*"
        rf"({_PERIOD_PREFIX})\s*(\d{{2,4}})\b",
        re.I,
    ),
)
_QUARTER_RE = re.compile(
    r"\b(?:q\s*(?P<q1>[1-4])|(?P<q2>[1-4])\s*q)\b",
    re.I,
)
_HALF_RE = re.compile(r"\b(?:h\s*(?P<h1>[12])|(?P<h2>[12])\s*h)\b", re.I)
_CY_RE = re.compile(r"\b(?:cy|calendar\s+year)\s*(?P<y>\d{4})\b", re.I)
_ISO_DATE_RE = re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})\b")
_TEXT_DATE_RE = re.compile(
    r"\b(?P<mon>[a-z]{3,9})\.?\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<y>\d{4})\b",
    re.I,
)
_DMY_DATE_RE = re.compile(
    r"\b(?P<d>\d{1,2})(?:st|nd|rd|th)?\s+(?P<mon>[a-z]{3,9})\.?,?\s+(?P<y>\d{4})\b",
    re.I,
)
_BARE_YEAR_RE = re.compile(r"^\s*(?P<y>\d{4})\s*$")


def _expand_year(token: str) -> int:
    n = int(token)
    if n >= 1000:
        return n
    return 2000 + n if n < 80 else 1900 + n


def _fy_bounds(end_year: int, fy_start_month: int) -> tuple[date, date]:
    if fy_start_month == 1:
        return date(end_year, 1, 1), date(end_year, 12, 31)
    start = date(end_year - 1, fy_start_month, 1)
    end_month = fy_start_month - 1 or 12
    end_year_actual = end_year if fy_start_month != 1 else end_year
    last_day = calendar.monthrange(end_year_actual, end_month)[1]
    return start, date(end_year_actual, end_month, last_day)


def _quarter_bounds(fy_start: date, q: int) -> tuple[date, date]:
    start_month_index = (fy_start.month - 1 + (q - 1) * 3) % 12
    start_year = fy_start.year + (fy_start.month - 1 + (q - 1) * 3) // 12
    start = date(start_year, start_month_index + 1, 1)
    end_month_index = (start_month_index + 2) % 12
    end_year = start_year + (start_month_index + 2) // 12
    last_day = calendar.monthrange(end_year, end_month_index + 1)[1]
    return start, date(end_year, end_month_index + 1, last_day)


def _match_multi_year(label: str) -> tuple[int, int, bool] | None:
    """Return ``(low_year, high_year, is_fiscal)`` if the label states a span of
    two years joined by a word, else ``None``. ``is_fiscal`` is true when either
    endpoint is explicitly a fiscal/financial year; a bare or calendar-year span
    resolves against calendar boundaries, matching bare-year handling elsewhere.
    """
    for pattern in _MULTI_YEAR_RES:
        m = pattern.search(label)
        if not m:
            continue
        pfx1, y1, pfx2, y2 = m.groups()
        a, b = _expand_year(y1), _expand_year(y2)
        if a == b:
            return None  # a single year written oddly, let the normal path handle it
        # "fy", "f.y.", "fiscal", "financial" all begin with "f"; "cy" / "calendar" do not
        is_fiscal = any(
            p is not None and p.strip().lower().startswith("f") for p in (pfx1, pfx2)
        )
        return min(a, b), max(a, b), is_fiscal
    return None


def parse_period(raw_label: str | None, *, fy_start_month: int | None = None) -> NormalizedPeriod:
    label = (raw_label or "").strip()
    if not label:
        return NormalizedPeriod(
            raw_label="", kind=PeriodKind.unknown, start_date=None, end_date=None
        )

    assumed = fy_start_month is None
    fy_month = fy_start_month or INDIA_FY_START_MONTH

    iso = _ISO_DATE_RE.search(label)
    if iso:
        d = date(int(iso["y"]), int(iso["m"]), int(iso["d"]))
        return _maybe_year_end(label, d, fy_month, assumed)

    text_date = _TEXT_DATE_RE.search(label) or _DMY_DATE_RE.search(label)
    if text_date and text_date["mon"].lower() in _MONTHS:
        d = date(int(text_date["y"]), _MONTHS[text_date["mon"].lower()], int(text_date["d"]))
        return _maybe_year_end(label, d, fy_month, assumed)

    multi = _match_multi_year(label)
    if multi:
        lo, hi, is_fiscal = multi
        if is_fiscal:
            start = _fy_bounds(lo, fy_month)[0]
            end = _fy_bounds(hi, fy_month)[1]
            return NormalizedPeriod(
                label, PeriodKind.multi_year, start, end, fy_month, assumed
            )
        return NormalizedPeriod(
            label, PeriodKind.multi_year, date(lo, 1, 1), date(hi, 12, 31), 1, False
        )

    fy = _FY_RE.search(label)
    span = fy or _BARE_SPAN_RE.search(label)
    quarter = _QUARTER_RE.search(label)
    half = _HALF_RE.search(label)

    if span:
        y1 = _expand_year(span["y1"])
        y2 = _expand_year(span["y2"]) if span["y2"] else y1
        end_year = max(y1, y2)
        fy_start, fy_end = _fy_bounds(end_year, fy_month)
        if quarter:
            q = int(quarter["q1"] or quarter["q2"])
            qs, qe = _quarter_bounds(fy_start, q)
            return NormalizedPeriod(label, PeriodKind.quarter, qs, qe, fy_month, assumed)
        if half:
            h = int(half["h1"] or half["h2"])
            hs = fy_start if h == 1 else _quarter_bounds(fy_start, 3)[0]
            he = _quarter_bounds(fy_start, 2)[1] if h == 1 else fy_end
            return NormalizedPeriod(label, PeriodKind.half, hs, he, fy_month, assumed)
        return NormalizedPeriod(label, PeriodKind.fiscal_year, fy_start, fy_end, fy_month, assumed)

    cy = _CY_RE.search(label)
    if cy:
        y = int(cy["y"])
        return NormalizedPeriod(
            label, PeriodKind.calendar_year, date(y, 1, 1), date(y, 12, 31), 1, False
        )

    bare = _BARE_YEAR_RE.match(label)
    if bare:
        y = int(bare["y"])
        return NormalizedPeriod(
            label, PeriodKind.calendar_year, date(y, 1, 1), date(y, 12, 31), 1, True
        )

    return NormalizedPeriod(label, PeriodKind.unknown, None, None)


def _maybe_year_end(label: str, d: date, fy_month: int, assumed: bool) -> NormalizedPeriod:
    """A date that lands on a fiscal-year boundary in a "year ended ..." phrase
    denotes the whole fiscal year, not that single day."""
    lower = label.lower()
    end_month = fy_month - 1 or 12
    is_year_end_phrase = any(
        p in lower for p in ("year ended", "year ending", "fy ended", "for the year")
    )
    if is_year_end_phrase and d.month == end_month:
        start, end = _fy_bounds(d.year, fy_month)
        return NormalizedPeriod(label, PeriodKind.fiscal_year, start, end, fy_month, assumed)
    return NormalizedPeriod(label, PeriodKind.date, d, d)


def periods_relation(a: NormalizedPeriod, b: NormalizedPeriod) -> str:
    """One of: equal, a_contains_b, b_contains_a, overlap, disjoint, unknown."""
    if not (a.resolved and b.resolved):
        return "unknown"
    a0, a1, b0, b1 = a.start_date, a.end_date, b.start_date, b.end_date
    if a0 == b0 and a1 == b1:
        return "equal"
    if a1 < b0 or b1 < a0:
        return "disjoint"
    if a0 <= b0 and a1 >= b1:
        return "a_contains_b"
    if b0 <= a0 and b1 >= a1:
        return "b_contains_a"
    return "overlap"

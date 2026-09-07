from __future__ import annotations

from datetime import date

import pytest

from app.normalization.dates import PeriodKind, parse_period, periods_relation


@pytest.mark.parametrize(
    ("label", "kind", "start", "end"),
    [
        ("FY24", PeriodKind.fiscal_year, date(2023, 4, 1), date(2024, 3, 31)),
        ("FY2024", PeriodKind.fiscal_year, date(2023, 4, 1), date(2024, 3, 31)),
        ("FY 2023-24", PeriodKind.fiscal_year, date(2023, 4, 1), date(2024, 3, 31)),
        ("FY2023-2024", PeriodKind.fiscal_year, date(2023, 4, 1), date(2024, 3, 31)),
        ("2025-26", PeriodKind.fiscal_year, date(2025, 4, 1), date(2026, 3, 31)),
        ("Q4 FY24", PeriodKind.quarter, date(2024, 1, 1), date(2024, 3, 31)),
        ("Q1 FY24", PeriodKind.quarter, date(2023, 4, 1), date(2023, 6, 30)),
        ("H1 FY24", PeriodKind.half, date(2023, 4, 1), date(2023, 9, 30)),
        ("CY2025", PeriodKind.calendar_year, date(2025, 1, 1), date(2025, 12, 31)),
        ("March 31, 2024", PeriodKind.date, date(2024, 3, 31), date(2024, 3, 31)),
        ("31 March 2024", PeriodKind.date, date(2024, 3, 31), date(2024, 3, 31)),
        ("2024-03-31", PeriodKind.date, date(2024, 3, 31), date(2024, 3, 31)),
    ],
)
def test_parse_period(label, kind, start, end) -> None:
    p = parse_period(label)
    assert p.kind is kind
    assert p.start_date == start
    assert p.end_date == end


def test_year_ended_phrase_denotes_the_whole_fiscal_year() -> None:
    p = parse_period("for the year ended March 31, 2024")
    assert p.kind is PeriodKind.fiscal_year
    assert (p.start_date, p.end_date) == (date(2023, 4, 1), date(2024, 3, 31))


def test_us_style_fiscal_year_when_convention_supplied() -> None:
    p = parse_period("FY2024", fy_start_month=1)
    assert (p.start_date, p.end_date) == (date(2024, 1, 1), date(2024, 12, 31))
    assert p.convention_assumed is False


def test_india_convention_is_flagged_assumed() -> None:
    assert parse_period("FY24").convention_assumed is True


def test_unparseable_label_is_unknown() -> None:
    p = parse_period("the reporting period")
    assert p.kind is PeriodKind.unknown
    assert not p.resolved


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("FY24", "FY 2023-24", "equal"),
        ("FY24", "for the year ended March 31, 2024", "equal"),
        ("FY24", "Q4 FY24", "a_contains_b"),
        ("Q4 FY24", "FY24", "b_contains_a"),
        ("FY24", "FY25", "disjoint"),
        ("H1 FY24", "Q2 FY24", "a_contains_b"),
        ("H1 FY24", "H2 FY24", "disjoint"),
        ("the period", "FY24", "unknown"),
    ],
)
def test_periods_relation(a, b, expected) -> None:
    assert periods_relation(parse_period(a), parse_period(b)) == expected

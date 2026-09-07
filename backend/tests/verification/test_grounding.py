from __future__ import annotations

from app.verification.grounding import check_grounding, normalize_for_grounding


def test_exact_substring_passes_with_offsets() -> None:
    chunk = "Intro sentence.\nFY24 consolidated EBITDA was INR 127 Crore.\nMore text."
    r = check_grounding("FY24 consolidated EBITDA was INR 127 Crore", chunk)
    assert r.passed
    assert chunk[r.matched_start : r.matched_end].lower().startswith("fy24 consolidated ebitda")


def test_whitespace_and_newline_differences_are_tolerated() -> None:
    chunk = "revenue    of\n8,142  crore   for the year"
    r = check_grounding("revenue of 8,142 crore for the year", chunk)
    assert r.passed


def test_line_break_hyphenation_is_repaired() -> None:
    chunk = "the state-\nment of profit and loss shows a gain"
    r = check_grounding("the statement of profit and loss shows a gain", chunk)
    assert r.passed


def test_smart_quotes_and_dashes_normalized() -> None:
    chunk = "management said “growth stayed strong” – a good sign"
    r = check_grounding('management said "growth stayed strong" - a good sign', chunk)
    assert r.passed


def test_non_substring_fails() -> None:
    chunk = "This paragraph is about logistics volumes and nothing else."
    r = check_grounding("EBITDA margin improved to 6.5 percent", chunk)
    assert not r.passed
    assert "not a contiguous substring" in r.reason


def test_too_short_evidence_is_rejected() -> None:
    r = check_grounding("127", "the value 127 appears here")
    assert not r.passed
    assert "too short" in r.reason


def test_normalizer_is_idempotent() -> None:
    s = "  Foo   BAR\n baz-\nqux "
    assert normalize_for_grounding(normalize_for_grounding(s)) == normalize_for_grounding(s)

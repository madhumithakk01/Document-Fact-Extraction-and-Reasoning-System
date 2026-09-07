from __future__ import annotations

from app.extraction.anchoring import anchor_evidence
from app.ingestion.types import Chunk


def chunk(text: str, char_start: int = 500) -> Chunk:
    return Chunk(
        page_number=7,
        index=3,
        text=text,
        char_start=char_start,
        char_end=char_start + len(text),
    )


def test_exact_match_is_document_relative() -> None:
    c = chunk("Header line.\nRevenue was 8,142 crore in FY24.\nFooter.", char_start=1000)
    a = anchor_evidence(c, "Revenue was 8,142 crore in FY24.")
    assert a is not None and a.exact
    assert a.char_start == 1000 + c.text.index("Revenue")
    assert a.char_end == a.char_start + len("Revenue was 8,142 crore in FY24.")
    assert a.page_number == 7
    assert c.text[a.char_start - 1000 : a.char_end - 1000] == a.matched_text


def test_whitespace_insensitive_match() -> None:
    c = chunk("EBITDA   margin\nimproved to\t6.5 percent this year.")
    a = anchor_evidence(c, "EBITDA margin improved to 6.5 percent")
    assert a is not None and not a.exact
    assert "6.5 percent" in a.matched_text


def test_smart_quote_and_dash_normalization() -> None:
    c = chunk("The board said “growth remained strong” – a clear signal.")
    a = anchor_evidence(c, '"growth remained strong" - a clear signal')
    assert a is not None


def test_token_span_tolerates_edge_words() -> None:
    c = chunk("In FY24 the consolidated profit after tax stood at 162 crore, a record.")
    a = anchor_evidence(c, "consolidated profit after tax stood at 162 crore")
    assert a is not None
    assert a.matched_text.startswith("consolidated")
    assert a.matched_text.endswith("162 crore")


def test_missing_evidence_returns_none() -> None:
    c = chunk("Nothing in here about the number you want.")
    assert anchor_evidence(c, "total addressable market of 200 billion dollars") is None


def test_blank_evidence_returns_none() -> None:
    assert anchor_evidence(chunk("text"), "   ") is None

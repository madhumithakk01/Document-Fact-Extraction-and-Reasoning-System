from __future__ import annotations

from app.ingestion.tokens import estimate_tokens, tail_by_tokens


def test_estimate_tokens_scales_with_length() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 400) == 100


def test_tail_returns_whole_string_when_within_budget() -> None:
    text = "short enough"
    assert tail_by_tokens(text, 100) == text


def test_tail_cuts_on_word_boundary() -> None:
    text = " ".join(f"word{i}" for i in range(200))
    tail = tail_by_tokens(text, 10)
    assert len(tail) <= 10 * 4 + 8
    assert not tail.startswith("ord")  # no mid-word cut
    assert tail.split()[-1] == "word199"

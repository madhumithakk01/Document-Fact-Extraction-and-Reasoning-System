"""Provider-agnostic token estimation.

Ingestion only needs a rough token count to size the carried-context window;
it must not pull in a tokenizer tied to one model family. The ~4-chars-per-token
rule of thumb is close enough for English prose and financial text.
"""

from __future__ import annotations

_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def tail_by_tokens(text: str, max_tokens: int) -> str:
    """Return the trailing slice of ``text`` that is at most ``max_tokens``,
    cut on a whitespace boundary so words are not split."""
    budget_chars = max_tokens * _CHARS_PER_TOKEN
    if len(text) <= budget_chars:
        return text.strip()
    window = text[-budget_chars:]
    first_space = window.find(" ")
    if first_space != -1:
        window = window[first_space + 1 :]
    return window.strip()

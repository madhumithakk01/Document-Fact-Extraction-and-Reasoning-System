"""Locate an evidence span inside its chunk and express it as a document offset.

Extraction models copy evidence closely but not always byte-for-byte -- a
collapsed newline, a normalized space, smart quotes. Anchoring tries an exact
match first, then a whitespace-insensitive match with full index mapping, then a
first-to-last-token span. Anything that still fails is left unanchored for the
grounding check to reject.
"""

from __future__ import annotations

import re

from app.extraction.schema import SourceAnchor
from app.ingestion.types import Chunk

_WS = re.compile(r"\s+")
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def _normalize(s: str) -> str:
    return _WS.sub(" ", s.translate(_QUOTES)).strip().lower()


def normalize_for_match(s: str) -> str:
    """Whitespace/quote/case-folded form used to test whether an evidence span
    belongs to a given page's text."""
    return _normalize(s)


def _build_norm_map(text: str) -> tuple[str, list[int]]:
    """Return (normalized_text, index_map) where index_map[i] is the offset in
    ``text`` of the i-th character of the normalized string."""
    norm_chars: list[str] = []
    index_map: list[int] = []
    prev_ws = True  # leading whitespace is dropped
    for i, ch in enumerate(text.translate(_QUOTES)):
        if ch.isspace():
            if prev_ws:
                continue
            norm_chars.append(" ")
            index_map.append(i)
            prev_ws = True
        else:
            norm_chars.append(ch.lower())
            index_map.append(i)
            prev_ws = False
    # drop trailing single space
    if norm_chars and norm_chars[-1] == " ":
        norm_chars.pop()
        index_map.pop()
    return "".join(norm_chars), index_map


def anchor_evidence(chunk: Chunk, evidence_text: str) -> SourceAnchor | None:
    if not evidence_text.strip():
        return None
    text = chunk.text

    # 1. exact
    pos = text.find(evidence_text)
    if pos != -1:
        return _anchor(
            chunk, pos, pos + len(evidence_text), text[pos : pos + len(evidence_text)], True
        )

    # 2. whitespace / quote-insensitive with index mapping
    norm_text, index_map = _build_norm_map(text)
    norm_ev = _normalize(evidence_text)
    if norm_ev:
        p = norm_text.find(norm_ev)
        if p != -1:
            start = index_map[p]
            end = index_map[p + len(norm_ev) - 1] + 1
            return _anchor(chunk, start, end, text[start:end], False)

        # 3. first-to-last token span (tolerates dropped/added words at edges)
        tokens = norm_ev.split()
        if len(tokens) >= 3:
            first, last = tokens[0], tokens[-1]
            fp = norm_text.find(first)
            lp = norm_text.rfind(last)
            if fp != -1 and lp != -1 and lp >= fp:
                start = index_map[fp]
                end = index_map[lp + len(last) - 1] + 1
                span = text[start:end]
                # guard against a runaway span matching most of the page
                if len(span) <= max(len(evidence_text) * 3, 200):
                    return _anchor(chunk, start, end, span, False)
    return None


def _anchor(
    chunk: Chunk, local_start: int, local_end: int, matched: str, exact: bool
) -> SourceAnchor:
    return SourceAnchor(
        chunk_index=chunk.index,
        page_number=chunk.page_number,
        char_start=chunk.char_start + local_start,
        char_end=chunk.char_start + local_end,
        matched_text=matched,
        exact=exact,
    )

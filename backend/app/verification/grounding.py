"""Deterministic grounding check (§6.3 step 1).

Is the extracted evidence span a real, contiguous substring of the source chunk
once whitespace, hyphenation, and unicode punctuation are normalized? No model
call. A failure means the fact is rejected outright -- the model quoted
something the page does not say.
"""

from __future__ import annotations

import re

from app.verification.schema import GroundingResult

_CHAR_MAP = {
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "-",
    "−": "-",
    " ": " ",
    " ": " ",
    "​": "",
    "‌": "",
    "‍": "",
    "﻿": "",
}
_TRANSLATION = str.maketrans(_CHAR_MAP)
_HYPHEN_LINEBREAK = re.compile(r"-[ \t]*\n[ \t]*")

# Below this many alphanumeric characters an "evidence span" is too thin to be a
# meaningful quote and matches something by accident.
_MIN_ALNUM = 4
# A short span that occurs this many times in the chunk is not a reliable anchor.
_MAX_OCCURRENCES = 4


def normalize_for_grounding(text: str) -> str:
    text = _HYPHEN_LINEBREAK.sub("", text)
    text = text.translate(_TRANSLATION)
    return " ".join(text.split()).lower()


def _normalize_with_index_map(text: str) -> tuple[str, list[int]]:
    """Normalized text and, for each normalized character, its offset in ``text``.

    Uses the same rules as ``normalize_for_grounding`` so a match here is a match
    there, but keeps the offsets needed to locate the span in the chunk.
    """
    chars: list[str] = []
    index_map: list[int] = []
    prev_space = True
    i = 0
    n = len(text)
    while i < n:
        m = _HYPHEN_LINEBREAK.match(text, i)
        if m:
            i = m.end()
            continue
        ch = text[i].translate(_TRANSLATION)
        if ch == "":
            i += 1
            continue
        if ch.isspace():
            if not prev_space:
                chars.append(" ")
                index_map.append(i)
                prev_space = True
        else:
            chars.append(ch.lower())
            index_map.append(i)
            prev_space = False
        i += 1
    if chars and chars[-1] == " ":
        chars.pop()
        index_map.pop()
    return "".join(chars), index_map


def check_grounding(evidence_text: str, chunk_text: str) -> GroundingResult:
    ev_norm = normalize_for_grounding(evidence_text)
    if sum(c.isalnum() for c in ev_norm) < _MIN_ALNUM:
        return GroundingResult(passed=False, reason="evidence span too short to ground")

    haystack, index_map = _normalize_with_index_map(chunk_text)
    pos = haystack.find(ev_norm)
    if pos == -1:
        return GroundingResult(
            passed=False,
            reason="evidence is not a contiguous substring of the source chunk",
            normalized_evidence=ev_norm,
        )
    if len(ev_norm) < 24 and haystack.count(ev_norm) > _MAX_OCCURRENCES:
        return GroundingResult(
            passed=False,
            reason="evidence span is too generic to anchor (matches many places)",
            normalized_evidence=ev_norm,
        )
    start = index_map[pos]
    end = index_map[pos + len(ev_norm) - 1] + 1
    return GroundingResult(
        passed=True,
        reason="evidence matches the source chunk",
        normalized_evidence=ev_norm,
        matched_start=start,
        matched_end=end,
    )

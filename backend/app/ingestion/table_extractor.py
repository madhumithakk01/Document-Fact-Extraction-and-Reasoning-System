"""Structured table extraction with a noise filter.

PyMuPDF's table finder is fast enough to run in the same pass as text
extraction. Its raw output still fires on ruled lines, single columns, and
table-of-contents dotted leaders, so this module keeps only grids that look
like real data tables and records how many leading rows are headers.
"""

from __future__ import annotations

import re

import pymupdf

from app.ingestion.types import BBox, Table

_MIN_ROWS = 2
_MIN_COLS = 2
_MIN_FILLED_CELLS = 4
_MAX_EMPTY_RATIO = 0.6
# A cell that is only dots / dots + a number is a TOC leader, not data.
_TOC_LEADER = re.compile(r"^[.…\s]*\d*$")
_NUMERIC = re.compile(r"[-+]?[\d,]*\.?\d")


def _clean(cell: str | None) -> str:
    return (cell or "").replace("\xad", "").replace("\n", " ").strip()


def _looks_like_toc(rows: list[list[str]]) -> bool:
    if len(rows) < 4:
        return False
    leader_rows = 0
    for r in rows:
        if not r:
            continue
        last = r[-1]
        joined = " ".join(r[:-1])
        if _TOC_LEADER.match(last) and joined and not _NUMERIC.search(joined):
            leader_rows += 1
    return leader_rows >= len(rows) * 0.6


def _guess_header_rows(rows: list[list[str]]) -> int:
    """First row is a header if it has no numeric cells and a later row does."""
    if len(rows) < 2:
        return 0
    first_numeric = any(_NUMERIC.search(c) for c in rows[0])
    rest_numeric = any(_NUMERIC.search(c) for r in rows[1:3] for c in r)
    return 0 if first_numeric or not rest_numeric else 1


def _accept(rows: list[list[str]]) -> bool:
    if len(rows) < _MIN_ROWS:
        return False
    n_cols = max((len(r) for r in rows), default=0)
    if n_cols < _MIN_COLS:
        return False
    cells = [c for r in rows for c in r]
    filled = sum(1 for c in cells if c)
    if filled < _MIN_FILLED_CELLS:
        return False
    if cells and (1 - filled / len(cells)) > _MAX_EMPTY_RATIO:
        return False
    return not _looks_like_toc(rows)


def tables_from_page(page: pymupdf.Page) -> list[Table]:
    """Accepted data tables on an already-open PyMuPDF page."""
    out: list[Table] = []
    try:
        finder = page.find_tables()
    except Exception:  # noqa: BLE001 - a finder failure must not abort ingestion
        return out
    for found in finder.tables:
        raw = found.extract() or []
        rows = [[_clean(c) for c in row] for row in raw]
        rows = [r for r in rows if any(r)]
        if not _accept(rows):
            continue
        x0, y0, x1, y1 = found.bbox
        out.append(
            Table(
                rows=rows,
                header_rows=_guess_header_rows(rows),
                bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
            )
        )
    return out

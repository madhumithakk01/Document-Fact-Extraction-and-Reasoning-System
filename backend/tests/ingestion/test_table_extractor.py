from __future__ import annotations

from app.ingestion.table_extractor import _accept, _guess_header_rows, _looks_like_toc


def test_rejects_single_column() -> None:
    assert not _accept([["a"], ["b"], ["c"]])


def test_rejects_mostly_empty_grid() -> None:
    assert not _accept([["a", "", ""], ["", "", ""], ["", "", "b"]])


def test_accepts_real_data_table() -> None:
    rows = [
        ["Metric", "FY24", "FY23"],
        ["Revenue", "8,142", "7,225"],
        ["EBITDA", "127", "-1,008"],
    ]
    assert _accept(rows)


def test_detects_table_of_contents_leader_rows() -> None:
    toc = [
        ["State of the Economy", "1"],
        ["External Sector", "..... 46"],
        ["Prices and Inflation", "...... 124"],
        ["Outlook", ".... 176"],
    ]
    assert _looks_like_toc(toc)
    assert not _accept(toc)


def test_header_row_guess() -> None:
    with_header = [["Name", "Value"], ["Revenue", "100"], ["Cost", "40"]]
    without_header = [["Revenue", "100"], ["Cost", "40"]]
    assert _guess_header_rows(with_header) == 1
    assert _guess_header_rows(without_header) == 0

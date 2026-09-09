"""The grounding metric must report drops, not just the survivor pass rate."""

from __future__ import annotations

import pytest

from app.evaluation.metrics import grounding_survivorship


def test_pass_rate_and_yield_rate_differ_when_candidates_were_dropped() -> None:
    # extractor proposed 20, kept 16 (4 dropped for schema/column reasons);
    # of the 16 that reached grounding, 15 passed.
    s = grounding_survivorship(
        per_document=[
            (
                {
                    "candidates_returned": 20,
                    "candidates_kept": 16,
                    "dropped_invalid": 3,
                    "dropped_no_column_context": 1,
                },
                16,
            )
        ],
        grounding_checks=16,
        grounding_pass=15,
    )

    assert s["candidates_considered"] == 20
    assert s["candidates_kept"] == 16
    assert s["candidates_dropped_pre_grounding"] == 4
    assert s["candidates_dropped_for_grounding"] == 1  # 16 checked - 15 passed
    assert s["grounding_yield_rate"] == pytest.approx(15 / 20)


def test_document_without_stats_falls_back_to_its_grounding_checks() -> None:
    s = grounding_survivorship(
        per_document=[({}, 10)],
        grounding_checks=10,
        grounding_pass=9,
    )
    assert s["candidates_considered"] == 10
    assert s["candidates_dropped_pre_grounding"] == 0
    assert s["candidates_dropped_for_grounding"] == 1
    assert s["grounding_yield_rate"] == pytest.approx(0.9)


def test_a_mix_of_documents_with_and_without_stats_is_not_undercounted() -> None:
    s = grounding_survivorship(
        per_document=[
            ({"candidates_returned": 10, "candidates_kept": 10}, 10),
            ({}, 4),  # legacy doc: 4 facts reached grounding, no stats recorded
        ],
        grounding_checks=14,
        grounding_pass=13,
    )
    assert s["candidates_considered"] == 14
    assert s["candidates_dropped_for_grounding"] == 1
    assert s["grounding_yield_rate"] == pytest.approx(13 / 14)


def test_zero_everything_is_safe() -> None:
    s = grounding_survivorship(per_document=[], grounding_checks=0, grounding_pass=0)
    assert s["candidates_considered"] == 0
    assert s["grounding_yield_rate"] == 0.0

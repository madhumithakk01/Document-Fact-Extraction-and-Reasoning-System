"""Independent dual-extraction corroboration: scoring and the precheck-only verdict."""

from __future__ import annotations

import pytest

from app.extraction.schema import CandidateFact
from app.verification.dual_extract import (
    CORROBORATED,
    UNCONFIRMED,
    _score,
    independent_corroborate,
)
from tests.extraction.conftest import fact_payload


def _cand(**over: object) -> CandidateFact:
    # a calendar-year label so the default carries no silent assumptions
    payload = fact_payload(period={"raw_label": "calendar year 2024"})
    payload.update(over)
    return CandidateFact.model_validate(payload)


def test_score_matches_the_specified_formula() -> None:
    assert _score(True, []) == pytest.approx(0.90)
    assert _score(False, []) == pytest.approx(0.50)
    assert _score(True, ["a", "b"]) == pytest.approx(0.70)
    assert _score(False, ["a"]) == pytest.approx(0.40)


def test_score_is_clamped_to_the_floor() -> None:
    assert _score(False, ["x"] * 20) == 0.05


def test_a_matching_blind_fact_corroborates_and_names_its_provider() -> None:
    primary = _cand()
    # same number, differently written unit -> the precheck resolves it
    blind = _cand(value={"comparator": "eq", "number": 8142.0, "unit": "Rs Crore"})

    result = independent_corroborate(primary, [blind], blind_provider="ollama")

    assert result.status == CORROBORATED
    assert result.corroborating_provider == "ollama"
    assert result.needs_human_review is False
    assert result.confidence == pytest.approx(_score(True, []))


def test_no_matching_blind_fact_is_single_source_and_needs_review() -> None:
    primary = _cand()
    blind = _cand(
        attribute="employee count",
        value={"comparator": "eq", "number": 45000.0, "unit": "people"},
    )

    result = independent_corroborate(primary, [blind], blind_provider="ollama")

    assert result.status == UNCONFIRMED
    assert result.needs_human_review is True
    assert result.corroborating_provider is None
    assert result.confidence == pytest.approx(_score(False, []))


def test_empty_blind_set_is_single_source() -> None:
    result = independent_corroborate(_cand(), [], blind_provider="ollama")
    assert result.status == UNCONFIRMED
    assert result.blind_fact_count == 0


def test_an_assumed_flag_on_the_primary_lowers_the_score() -> None:
    # no comparator on the primary -> "comparator_unspecified" assumption
    primary = _cand(value={"number": 8142.0, "unit": "INR Crore"})
    blind = _cand(value={"number": 8142.0, "unit": "INR Crore"})

    result = independent_corroborate(primary, [blind], blind_provider="ollama")

    assert result.status == CORROBORATED
    assert result.confidence == pytest.approx(_score(True, ["comparator_unspecified"]))

"""The auto-correction audit record diffs the stored fact against the fix."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.extraction.schema import CandidateFact
from app.models.fact import Fact
from app.verification.audit import build_correction_record

_VALUE = {"comparator": "eq", "number": 120.0, "unit": "INR Crore"}


def _fact(**over: object) -> Fact:
    base: dict = {
        "fact_id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "document_id": uuid.uuid4(),
        "fact_kind": "quantitative",
        "entity": "Acme",
        "entity_resolved": True,
        "attribute": "revenue",
        "value": dict(_VALUE),
        "period": {"raw_label": "FY24"},
        "qualifiers": {"basis": "consolidated"},
        "evidence_text": "revenue was 120",
    }
    base.update(over)
    return Fact(**base)


def _candidate(**over: object) -> CandidateFact:
    base: dict = {
        "fact_kind": "quantitative",
        "entity": "Acme",
        "entity_resolved": True,
        "attribute": "revenue",
        "value": dict(_VALUE),
        "period": {"raw_label": "FY24"},
        "qualifiers": {"basis": "consolidated"},
        "evidence_text": "revenue was 120",
    }
    base.update(over)
    return CandidateFact.model_validate(base)


def test_no_change_yields_no_record() -> None:
    assert build_correction_record(_fact(), _candidate()) is None


def test_number_correction_records_old_and_new() -> None:
    fact = _fact()
    corrected = _candidate(
        value={"comparator": "eq", "number": 127.0, "unit": "INR Crore"}
    )

    record = build_correction_record(fact, corrected)

    assert record is not None
    assert record["fact_id"] == str(fact.fact_id)
    assert record["corrected_by"] == "verifier"
    datetime.fromisoformat(record["at"])  # parses, i.e. a real timestamp
    assert set(record["changes"]) == {"value"}
    assert record["changes"]["value"]["old"]["number"] == 120.0
    assert record["changes"]["value"]["new"]["number"] == 127.0


def test_multiple_fields_are_each_recorded() -> None:
    record = build_correction_record(
        _fact(),
        _candidate(
            entity="Acme Corporation",
            value={"comparator": "eq", "number": 120.0, "unit": "INR"},
        ),
    )

    assert record is not None
    assert set(record["changes"]) == {"entity", "value"}
    assert record["changes"]["entity"] == {"old": "Acme", "new": "Acme Corporation"}


def test_corrected_by_is_overridable() -> None:
    record = build_correction_record(
        _fact(), _candidate(attribute="total revenue"), corrected_by="reviewer"
    )
    assert record is not None
    assert record["corrected_by"] == "reviewer"

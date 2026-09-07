from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.extraction.schema import (
    EXTRACTION_JSON_SCHEMA,
    CandidateFact,
    Comparator,
    FactKind,
)


def test_json_schema_shape() -> None:
    assert EXTRACTION_JSON_SCHEMA["required"] == ["facts"]
    item = EXTRACTION_JSON_SCHEMA["properties"]["facts"]["items"]
    assert item["additionalProperties"] is False
    for key in ("fact_kind", "entity", "attribute", "value", "period", "evidence_text"):
        assert key in item["properties"]


def test_candidate_fact_minimal_valid() -> None:
    fact = CandidateFact.model_validate(
        {
            "fact_kind": "status",
            "entity": "Delhivery",
            "attribute": "listing status",
            "evidence_text": "the Company was listed on the exchanges",
        }
    )
    assert fact.fact_kind is FactKind.status
    assert fact.entity_resolved is True
    assert fact.value.comparator is None


def test_blank_required_field_rejected() -> None:
    with pytest.raises(ValidationError):
        CandidateFact.model_validate(
            {"fact_kind": "qualitative", "entity": "  ", "attribute": "x", "evidence_text": "y"}
        )


def test_confidence_is_clamped() -> None:
    fact = CandidateFact.model_validate(
        {
            "fact_kind": "qualitative",
            "entity": "x",
            "attribute": "y",
            "evidence_text": "z",
            "extraction_confidence": 4.2,
        }
    )
    assert fact.extraction_confidence == 1.0


def test_comparator_enum_accepts_inequalities() -> None:
    fact = CandidateFact.model_validate(
        {
            "fact_kind": "quantitative",
            "entity": "x",
            "attribute": "shipments",
            "evidence_text": "over 2.8 billion shipments",
            "value": {"comparator": "gt", "number": 2.8e9, "unit": "shipments"},
        }
    )
    assert fact.value.comparator is Comparator.gt

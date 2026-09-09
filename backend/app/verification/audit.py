"""Structured audit record for verifier auto-corrections.

When the verification loop overwrites a stored fact with a corrected value, the
row that existed before the overwrite would otherwise be lost. This builds a
field-level before/after record so the correction stays inspectable after the
fact.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.extraction.schema import CandidateFact
from app.models.fact import Fact

# The fact fields the verifier is allowed to overwrite (see persist_verification).
_AUDITED_FIELDS = ("entity", "entity_resolved", "attribute", "value", "period", "qualifiers")


def _corrected_snapshot(c: CandidateFact) -> dict:
    return {
        "entity": c.entity,
        "entity_resolved": c.entity_resolved,
        "attribute": c.attribute,
        "value": c.value.model_dump(exclude_none=True),
        "period": c.period.model_dump(exclude_none=True),
        "qualifiers": c.qualifiers,
    }


def build_correction_record(
    fact: Fact,
    corrected: CandidateFact,
    *,
    corrected_by: str = "verifier",
) -> dict | None:
    """Diff the stored fact against the corrected candidate.

    Returns ``None`` when nothing actually changed, otherwise a record of the
    shape ``{fact_id, corrected_by, at, changes: {field: {old, new}}}``.
    """
    before = {field: getattr(fact, field) for field in _AUDITED_FIELDS}
    after = _corrected_snapshot(corrected)

    changes = {
        field: {"old": before[field], "new": after[field]}
        for field in _AUDITED_FIELDS
        if before[field] != after[field]
    }
    if not changes:
        return None

    return {
        "fact_id": str(fact.fact_id),
        "corrected_by": corrected_by,
        "at": datetime.now(UTC).isoformat(),
        "changes": changes,
    }

"""Typed structures for extraction and the JSON Schema handed to the provider.

The provider is constrained to return ``{"facts": [ ... ]}`` matching
``EXTRACTION_JSON_SCHEMA``. The Pydantic models here validate that response and
are the structures every later stage consumes -- no ad hoc dicts.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class FactKind(StrEnum):
    quantitative = "quantitative"
    status = "status"
    qualitative = "qualitative"


class Comparator(StrEnum):
    """How a quantitative value relates to the stated number.

    Never defaults to ``eq``: approximate language ("over", "about", "up to")
    must map to the matching bound so a later comparison does not read an
    approximation as an exact figure.
    """

    eq = "eq"
    approx = "approx"
    gt = "gt"
    gte = "gte"
    lt = "lt"
    lte = "lte"
    range = "range"


class VerificationStatus(StrEnum):
    pending = "pending"
    verified = "verified"
    auto_corrected = "auto_corrected"
    needs_review = "needs_review"
    rejected = "rejected"


class ExtractedValue(BaseModel):
    comparator: Comparator | None = None
    number: float | None = None
    number_high: float | None = None  # upper bound when comparator is ``range``
    unit: str | None = None
    state: str | None = None  # status facts, e.g. "profitable", "listed"
    text: str | None = None  # qualitative facts

    @field_validator("unit", "state", "text")
    @classmethod
    def _blank_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ExtractedPeriod(BaseModel):
    raw_label: str | None = None
    start_date: str | None = None  # ISO 8601; only when the FY convention is stated
    end_date: str | None = None


class CandidateFact(BaseModel):
    """One fact as returned by the model, before anchoring."""

    fact_kind: FactKind
    entity: str
    entity_resolved: bool = True
    attribute: str
    value: ExtractedValue = Field(default_factory=ExtractedValue)
    period: ExtractedPeriod = Field(default_factory=ExtractedPeriod)
    qualifiers: dict[str, Any] = Field(default_factory=dict)
    evidence_text: str
    extraction_confidence: float = 0.5

    @field_validator("entity", "attribute", "evidence_text")
    @classmethod
    def _required_nonblank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("extraction_confidence")
    @classmethod
    def _clamp_conf(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class SourceAnchor(BaseModel):
    """Where the evidence span sits in the source document."""

    chunk_id: str | None = None
    chunk_index: int
    page_number: int
    char_start: int  # offset within the document's concatenated page text
    char_end: int
    matched_text: str  # the exact source substring the evidence resolved to
    exact: bool  # True if evidence_text matched verbatim, False if whitespace-normalized


class AnchoredFact(BaseModel):
    """A candidate fact plus its resolved location and bookkeeping."""

    candidate: CandidateFact
    anchor: SourceAnchor | None
    document_id: str | None = None
    verification_status: VerificationStatus = VerificationStatus.pending
    notes: list[str] = Field(default_factory=list)

    @property
    def anchored(self) -> bool:
        return self.anchor is not None


class ExtractionStats(BaseModel):
    chunks_seen: int = 0
    chunks_called: int = 0
    chunks_failed: int = 0
    llm_calls: int = 0
    facts_returned: int = 0
    facts_kept: int = 0
    unanchored: int = 0
    dropped_no_column_context: int = 0
    dropped_invalid: int = 0
    comparator_repaired: int = 0
    by_kind: dict[str, int] = Field(default_factory=dict)


class ExtractionResult(BaseModel):
    document_filename: str
    content_hash: str
    facts: list[AnchoredFact]
    stats: ExtractionStats


# --- JSON Schema sent to the provider (kept flat and strict-mode friendly) ---

_VALUE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "comparator": {
            "type": ["string", "null"],
            "enum": ["eq", "approx", "gt", "gte", "lt", "lte", "range", None],
            "description": (
                "Required for quantitative facts. Use 'eq' only for an exact stated "
                "figure. 'over'/'more than' -> gt, 'at least' -> gte, 'up to'/'no more "
                "than' -> lte, 'under'/'less than' -> lt, 'about'/'around'/'~'/"
                "'approximately'/'nearly' -> approx, a stated low-high band -> range."
            ),
        },
        "number": {"type": ["number", "null"]},
        "number_high": {
            "type": ["number", "null"],
            "description": "Upper bound; only when comparator is 'range'.",
        },
        "unit": {
            "type": ["string", "null"],
            "description": "Verbatim unit as written, e.g. 'INR Crore', '%', 'Mn tonnes'.",
        },
        "state": {
            "type": ["string", "null"],
            "description": "For status facts: the state asserted, e.g. 'profitable', 'listed'.",
        },
        "text": {
            "type": ["string", "null"],
            "description": "For qualitative facts: the claim in a short normalized phrase.",
        },
    },
    "required": ["comparator", "number", "number_high", "unit", "state", "text"],
}

_PERIOD_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "raw_label": {
            "type": ["string", "null"],
            "description": "The period exactly as written, e.g. 'FY24', 'Q4 FY2023-24', 'CY2025'.",
        },
        "start_date": {
            "type": ["string", "null"],
            "description": (
                "ISO date. Only fill when the document states its fiscal-year convention."
            ),
        },
        "end_date": {"type": ["string", "null"]},
    },
    "required": ["raw_label", "start_date", "end_date"],
}

_FACT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "fact_kind": {"type": "string", "enum": ["quantitative", "status", "qualitative"]},
        "entity": {
            "type": "string",
            "description": (
                "The specific thing the fact is about. Resolve pronouns and "
                "'the Company' using the continued-from-previous-page context."
            ),
        },
        "entity_resolved": {
            "type": "boolean",
            "description": (
                "False if the entity had to be inferred from carried context "
                "rather than stated on this page."
            ),
        },
        "attribute": {
            "type": "string",
            "description": (
                "What is being measured or asserted, open vocabulary, e.g. "
                "'consolidated EBITDA', 'real GDP growth', 'CEO'."
            ),
        },
        "value": _VALUE_SCHEMA,
        "period": _PERIOD_SCHEMA,
        "qualifiers": {
            "type": "object",
            "description": (
                "Anything needed to compare this fact correctly later: basis, currency, "
                "audited, forecast_vs_actual, asserting_party, consolidated_vs_standalone. "
                "For a value read from a table you MUST include the column header as "
                "'column_header' and the row label as 'row_header'."
            ),
            "additionalProperties": {"type": "string"},
        },
        "evidence_text": {
            "type": "string",
            "description": (
                "A verbatim span copied from the page that states this fact. Do not paraphrase."
            ),
        },
        "extraction_confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": [
        "fact_kind",
        "entity",
        "entity_resolved",
        "attribute",
        "value",
        "period",
        "qualifiers",
        "evidence_text",
        "extraction_confidence",
    ],
}

EXTRACTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "facts": {
            "type": "array",
            "items": _FACT_SCHEMA,
            "description": "Every atomic, independently checkable fact on the page. Empty if none.",
        }
    },
    "required": ["facts"],
}

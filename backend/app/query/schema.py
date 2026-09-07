"""Typed structures for the reasoning console."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Citation(BaseModel):
    marker: str  # "F1", "F2", ... as used inline in the answer
    fact_id: str
    entity: str
    attribute: str
    value_summary: str
    period: str | None
    verification_status: str
    document_filename: str
    page_number: int | None
    evidence_text: str


class Disagreement(BaseModel):
    relationship_type: str  # contradicts | reconciled_by_context
    reconciliation_basis: str | None
    explanation: str
    marker_a: str
    marker_b: str
    fact_a_id: str
    fact_b_id: str
    fact_a_summary: str
    fact_b_summary: str


class QueryTraceEntry(BaseModel):
    step: int
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    result: str = ""


class QueryResult(BaseModel):
    question: str
    answer: str  # markdown, with inline [F1]-style citation markers
    citations: list[Citation] = Field(default_factory=list)
    disagreements: list[Disagreement] = Field(default_factory=list)
    trace: list[QueryTraceEntry] = Field(default_factory=list)
    fact_ids_considered: list[str] = Field(default_factory=list)
    tool_calls_used: int = 0

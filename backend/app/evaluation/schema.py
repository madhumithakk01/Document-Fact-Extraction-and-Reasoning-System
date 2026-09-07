"""Shapes for the evaluation report (also the API response model)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DocumentEvaluation(BaseModel):
    document_id: uuid.UUID
    filename: str
    processed_at: datetime | None
    facts_total: int
    facts_by_status: dict[str, int]
    grounding_checks: int
    grounding_pass: int
    grounding_pass_rate: float


class TimelinePoint(BaseModel):
    """Cumulative metrics as of the moment this document finished processing."""

    index: int  # 1-based position in processing order
    document_id: uuid.UUID
    filename: str
    cumulative_facts: int
    grounding_pass_rate: float
    verified_rate: float
    needs_review_rate: float


class EvaluationReport(BaseModel):
    grounding_checks: int
    grounding_pass: int
    grounding_pass_rate: float

    independent_verify_calls: int
    independent_verify_breakdown: dict[str, int]

    facts_total: int
    facts_by_status: dict[str, int]
    verified_rate: float
    auto_correction_rate: float
    needs_review_rate: float
    rejected_rate: float

    per_document: list[DocumentEvaluation] = Field(default_factory=list)
    timeline: list[TimelinePoint] = Field(default_factory=list)

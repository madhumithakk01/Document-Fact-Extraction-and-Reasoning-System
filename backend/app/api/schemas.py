"""Request and response models for the HTTP API.

These are the public shapes. ORM rows never leave a handler directly; each is
mapped to one of these first.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.concept import CanonicalConcept
from app.models.document import Document
from app.models.fact import Fact
from app.models.project import Project
from app.models.relationship import FactRelationship


# --- projects ---
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectOut(BaseModel):
    project_id: uuid.UUID
    name: str
    created_at: datetime
    domain_profile: dict[str, Any]

    @classmethod
    def of(cls, p: Project) -> ProjectOut:
        return cls(
            project_id=p.project_id,
            name=p.name,
            created_at=p.created_at,
            domain_profile=p.domain_profile,
        )


class ProjectSummary(ProjectOut):
    document_count: int
    fact_count: int
    facts_by_status: dict[str, int]
    relationship_count: int
    relationships_by_type: dict[str, int]
    concept_count: int
    sub_cluster_count: int


# --- documents ---
class DocumentOut(BaseModel):
    document_id: uuid.UUID
    project_id: uuid.UUID
    filename: str
    content_hash: str
    byte_size: int
    content_type_detected: str
    processing_status: str
    processing_error: str | None
    processing_detail: str | None
    pages_total: int | None
    pages_processed: int | None
    page_count: int
    ocr_page_count: int
    routing_profile: dict[str, Any]
    sub_cluster_id: str | None
    off_domain: bool
    uploaded_at: datetime | None
    created_at: datetime

    @classmethod
    def of(cls, d: Document) -> DocumentOut:
        return cls(
            document_id=d.document_id,
            project_id=d.project_id,
            filename=d.filename,
            content_hash=d.content_hash,
            byte_size=d.byte_size,
            content_type_detected=d.content_type_detected,
            processing_status=d.processing_status,
            processing_error=d.processing_error,
            processing_detail=d.processing_detail,
            pages_total=d.pages_total,
            pages_processed=d.pages_processed,
            page_count=d.page_count,
            ocr_page_count=d.ocr_page_count,
            routing_profile=d.routing_profile,
            sub_cluster_id=d.sub_cluster_id,
            off_domain=d.off_domain,
            uploaded_at=d.uploaded_at,
            created_at=d.created_at,
        )


class DocumentStatus(BaseModel):
    document_id: uuid.UUID
    processing_status: str
    processing_error: str | None
    processing_detail: str | None
    pages_total: int | None
    pages_processed: int | None
    page_count: int
    chunk_count: int
    fact_count: int
    facts_by_status: dict[str, int]
    relationship_count: int


# --- facts ---
class FactOut(BaseModel):
    fact_id: uuid.UUID
    project_id: uuid.UUID
    document_id: uuid.UUID
    chunk_id: uuid.UUID | None
    page_number: int | None
    fact_kind: str
    entity: str
    entity_resolved: bool
    attribute: str
    value: dict[str, Any]
    period: dict[str, Any]
    qualifiers: dict[str, Any]
    evidence_text: str
    verification_status: str
    extraction_confidence: float
    verifier_confidence: float | None
    provider_used: str | None
    notes: list[Any]
    corrections: list[Any]
    source_anchor: dict[str, Any]
    created_at: datetime

    @classmethod
    def of(cls, f: Fact) -> FactOut:
        return cls(
            fact_id=f.fact_id,
            project_id=f.project_id,
            document_id=f.document_id,
            chunk_id=f.chunk_id,
            page_number=f.page_number,
            fact_kind=f.fact_kind,
            entity=f.entity,
            entity_resolved=f.entity_resolved,
            attribute=f.attribute,
            value=f.value,
            period=f.period,
            qualifiers=f.qualifiers,
            evidence_text=f.evidence_text,
            verification_status=f.verification_status,
            extraction_confidence=f.extraction_confidence,
            verifier_confidence=f.verifier_confidence,
            provider_used=f.provider_used,
            notes=f.notes,
            corrections=f.corrections,
            source_anchor=f.source_anchor,
            created_at=f.created_at,
        )


class BBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class EvidenceOut(BaseModel):
    fact_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: int | None
    evidence_text: str
    surrounding_text: str
    page_image_url: str | None
    page_width: float | None
    page_height: float | None
    highlight_bboxes: list[BBox]
    highlight_bboxes_normalized: list[BBox]


# --- relationships ---
class RelationshipOut(BaseModel):
    relationship_id: uuid.UUID
    project_id: uuid.UUID
    fact_a_id: uuid.UUID
    fact_b_id: uuid.UUID
    relationship_type: str
    reconciliation_basis: str | None
    explanation: str
    confidence: float
    investigation_trail: list[Any]
    created_at: datetime

    @classmethod
    def of(cls, r: FactRelationship) -> RelationshipOut:
        return cls(
            relationship_id=r.relationship_id,
            project_id=r.project_id,
            fact_a_id=r.fact_a_id,
            fact_b_id=r.fact_b_id,
            relationship_type=r.relationship_type,
            reconciliation_basis=r.reconciliation_basis,
            explanation=r.explanation,
            confidence=r.confidence,
            investigation_trail=r.investigation_trail,
            created_at=r.created_at,
        )


class RelationshipDetail(RelationshipOut):
    fact_a: FactOut
    fact_b: FactOut


# --- ontology ---
class ConceptOut(BaseModel):
    concept_id: uuid.UUID
    kind: str
    canonical_name: str
    raw_aliases: list[str]
    first_seen_document_id: uuid.UUID | None
    first_seen_at: datetime | None

    @classmethod
    def of(cls, c: CanonicalConcept) -> ConceptOut:
        return cls(
            concept_id=c.concept_id,
            kind=c.kind,
            canonical_name=c.canonical_name,
            raw_aliases=list(c.raw_aliases or []),
            first_seen_document_id=c.first_seen_document_id,
            first_seen_at=c.first_seen_at,
        )


class OntologyGroup(BaseModel):
    document_id: uuid.UUID | None
    document_filename: str | None
    concepts: list[ConceptOut]


class OntologyOut(BaseModel):
    groups: list[OntologyGroup]


# evaluation report lives in app/evaluation/schema.py


# --- query (reasoning console) ---
class QueryRequest(BaseModel):
    question: str = Field(min_length=1)

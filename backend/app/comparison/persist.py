"""Persist comparison outputs: canonical concepts and fact relationships."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.concept import CanonicalConcept
from app.models.relationship import FactRelationship


async def upsert_concept(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    kind: str,
    canonical_name: str,
    aliases: list[str],
    first_seen_document_id: uuid.UUID | None = None,
) -> CanonicalConcept:
    existing = (
        await session.execute(
            select(CanonicalConcept).where(
                CanonicalConcept.project_id == project_id,
                CanonicalConcept.kind == kind,
                CanonicalConcept.canonical_name == canonical_name,
            )
        )
    ).scalar_one_or_none()

    merged_aliases = sorted({*(a.strip() for a in aliases if a and a.strip())})

    if existing is None:
        concept = CanonicalConcept(
            concept_id=uuid.uuid4(),
            project_id=project_id,
            kind=kind,
            canonical_name=canonical_name,
            raw_aliases=merged_aliases,
            first_seen_document_id=first_seen_document_id,
            first_seen_at=datetime.now(UTC),
        )
        session.add(concept)
        await session.flush()
        return concept

    existing.raw_aliases = sorted({*existing.raw_aliases, *merged_aliases})
    if existing.first_seen_document_id is None and first_seen_document_id is not None:
        existing.first_seen_document_id = first_seen_document_id
        existing.first_seen_at = datetime.now(UTC)
    await session.flush()
    return existing


def _ordered(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Store the pair in a stable order so (a,b) and (b,a) are one row."""
    return (a, b) if str(a) <= str(b) else (b, a)


async def persist_relationship(
    session: AsyncSession,
    project_id: uuid.UUID,
    fact_a_id: uuid.UUID,
    fact_b_id: uuid.UUID,
    *,
    relationship_type: str,
    explanation: str,
    confidence: float,
    reconciliation_basis: str | None = None,
    investigation_trail: list[dict[str, Any]] | None = None,
) -> FactRelationship:
    a_id, b_id = _ordered(fact_a_id, fact_b_id)
    existing = (
        await session.execute(
            select(FactRelationship).where(
                FactRelationship.fact_a_id == a_id,
                FactRelationship.fact_b_id == b_id,
            )
        )
    ).scalar_one_or_none()

    trail = investigation_trail or []
    if existing is None:
        row = FactRelationship(
            relationship_id=uuid.uuid4(),
            project_id=project_id,
            fact_a_id=a_id,
            fact_b_id=b_id,
            relationship_type=relationship_type,
            reconciliation_basis=reconciliation_basis,
            explanation=explanation,
            confidence=confidence,
            investigation_trail=trail,
        )
        session.add(row)
        await session.flush()
        return row

    existing.relationship_type = relationship_type
    existing.reconciliation_basis = reconciliation_basis
    existing.explanation = explanation
    existing.confidence = confidence
    existing.investigation_trail = trail
    await session.flush()
    return existing

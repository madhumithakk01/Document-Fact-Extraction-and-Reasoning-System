"""Persist confirmed concept merges as CanonicalConcept rows (ontology view)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.concept import CanonicalConcept


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

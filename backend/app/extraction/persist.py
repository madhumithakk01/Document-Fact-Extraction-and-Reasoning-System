"""Write extracted facts to the ``facts`` table.

Facts are stored unverified. Re-running extraction for a document replaces its
existing ``pending`` facts; anything already moved past ``pending`` by the
verification loop is left untouched.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extraction.schema import ExtractionResult
from app.models.document import Chunk
from app.models.fact import Fact
from app.normalization.assumptions import detect_assumptions, penalize_confidence


async def persist_facts(
    session: AsyncSession,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    result: ExtractionResult,
) -> list[Fact]:
    chunk_id_by_index = dict(
        (
            await session.execute(
                select(Chunk.chunk_index, Chunk.chunk_id).where(Chunk.document_id == document_id)
            )
        ).all()
    )

    await session.execute(
        delete(Fact).where(
            Fact.document_id == document_id,
            Fact.verification_status == "pending",
        )
    )

    rows: list[Fact] = []
    for af in result.facts:
        c = af.candidate
        anchor = af.anchor
        value = c.value.model_dump(exclude_none=True)
        period = c.period.model_dump(exclude_none=True)

        assumed = detect_assumptions(
            fact_kind=c.fact_kind.value,
            entity_resolved=c.entity_resolved,
            value=value,
            period_label=period.get("raw_label"),
        )
        qualifiers = {**c.qualifiers, "assumed": assumed} if assumed else c.qualifiers

        row = Fact(
            fact_id=uuid.uuid4(),
            project_id=project_id,
            document_id=document_id,
            chunk_id=(chunk_id_by_index.get(anchor.chunk_index) if anchor is not None else None),
            source_anchor=anchor.model_dump() if anchor is not None else {},
            page_number=anchor.page_number if anchor is not None else None,
            fact_kind=c.fact_kind.value,
            entity=c.entity,
            entity_resolved=c.entity_resolved,
            attribute=c.attribute,
            value=value,
            period=period,
            qualifiers=qualifiers,
            evidence_text=c.evidence_text,
            verification_status=af.verification_status.value,
            extraction_confidence=penalize_confidence(c.extraction_confidence, assumed),
            provider_used=af.provider_used,
            notes=af.notes,
        )
        session.add(row)
        rows.append(row)

    await session.flush()
    return rows

"""Embedding candidate generation (§6.5).

For a fact, find the other facts in the *same project* and *same fact_kind* whose
``entity + attribute + qualifiers`` embedding is nearest, using the pgvector
cosine index. These are the pairs worth running the pre-check and, if needed,
adjudication on.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fact import Fact

# cosine distance (0 = identical, 2 = opposite); above this the pair is unrelated
_MAX_COSINE_DISTANCE = 0.45
_USABLE_STATUSES = ("verified", "auto_corrected")


@dataclass(frozen=True, slots=True)
class Candidate:
    fact: Fact
    cosine_distance: float


async def candidates_for_fact(
    session: AsyncSession,
    project_id: uuid.UUID,
    fact: Fact,
    *,
    k: int = 10,
    max_distance: float = _MAX_COSINE_DISTANCE,
    include_same_document: bool = True,
) -> list[Candidate]:
    if fact.embedding is None:
        return []

    distance = Fact.embedding.cosine_distance(fact.embedding).label("distance")
    stmt = (
        select(Fact, distance)
        .where(
            Fact.project_id == project_id,
            Fact.fact_id != fact.fact_id,
            Fact.fact_kind == fact.fact_kind,
            Fact.verification_status.in_(_USABLE_STATUSES),
            Fact.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(k)
    )
    if not include_same_document:
        stmt = stmt.where(Fact.document_id != fact.document_id)

    rows = (await session.execute(stmt)).all()
    return [
        Candidate(fact=row[0], cosine_distance=float(row[1]))
        for row in rows
        if row[1] <= max_distance
    ]

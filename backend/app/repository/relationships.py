"""Project-scoped relationship reads."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from app.models.relationship import FactRelationship
from app.repository.scope import ProjectScope, scoped_select


async def list_relationships(
    scope: ProjectScope,
    *,
    relationship_type: str | None = None,
    min_confidence: float | None = None,
    fact_id: uuid.UUID | None = None,
) -> Sequence[FactRelationship]:
    stmt = scoped_select(FactRelationship, scope)
    if relationship_type is not None:
        stmt = stmt.where(FactRelationship.relationship_type == relationship_type)
    if min_confidence is not None:
        stmt = stmt.where(FactRelationship.confidence >= min_confidence)
    if fact_id is not None:
        stmt = stmt.where(
            (FactRelationship.fact_a_id == fact_id) | (FactRelationship.fact_b_id == fact_id)
        )
    stmt = stmt.order_by(FactRelationship.confidence.desc())
    return (await scope.session.execute(stmt)).scalars().all()


async def get_relationship(
    scope: ProjectScope, relationship_id: uuid.UUID
) -> FactRelationship | None:
    stmt = scoped_select(
        FactRelationship, scope, FactRelationship.relationship_id == relationship_id
    )
    return (await scope.session.execute(stmt)).scalar_one_or_none()

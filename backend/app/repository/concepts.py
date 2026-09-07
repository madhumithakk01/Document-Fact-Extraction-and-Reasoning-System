"""Project-scoped canonical-concept reads (ontology view)."""

from __future__ import annotations

from collections.abc import Sequence

from app.models.concept import CanonicalConcept
from app.repository.scope import ProjectScope, scoped_select


async def list_concepts(
    scope: ProjectScope, *, kind: str | None = None
) -> Sequence[CanonicalConcept]:
    stmt = scoped_select(CanonicalConcept, scope)
    if kind is not None:
        stmt = stmt.where(CanonicalConcept.kind == kind)
    stmt = stmt.order_by(CanonicalConcept.first_seen_at.asc().nulls_last())
    return (await scope.session.execute(stmt)).scalars().all()

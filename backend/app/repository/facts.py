"""Project-scoped fact reads."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from app.models.fact import Fact
from app.repository.scope import ProjectScope, scoped_select


async def list_facts(
    scope: ProjectScope,
    *,
    entity: str | None = None,
    attribute: str | None = None,
    fact_kind: str | None = None,
    verification_status: str | None = None,
    document_id: uuid.UUID | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> Sequence[Fact]:
    stmt = scoped_select(Fact, scope)
    if entity is not None:
        stmt = stmt.where(Fact.entity == entity)
    if attribute is not None:
        stmt = stmt.where(Fact.attribute == attribute)
    if fact_kind is not None:
        stmt = stmt.where(Fact.fact_kind == fact_kind)
    if verification_status is not None:
        stmt = stmt.where(Fact.verification_status == verification_status)
    if document_id is not None:
        stmt = stmt.where(Fact.document_id == document_id)
    stmt = stmt.order_by(Fact.created_at.desc()).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return (await scope.session.execute(stmt)).scalars().all()


async def get_fact(scope: ProjectScope, fact_id: uuid.UUID) -> Fact | None:
    stmt = scoped_select(Fact, scope, Fact.fact_id == fact_id)
    return (await scope.session.execute(stmt)).scalar_one_or_none()


async def count_facts_by_status(scope: ProjectScope) -> dict[str, int]:
    from sqlalchemy import func

    stmt = (
        scoped_select(Fact, scope)
        .with_only_columns(Fact.verification_status, func.count())
        .group_by(Fact.verification_status)
    )
    rows = (await scope.session.execute(stmt)).all()
    return dict(rows)

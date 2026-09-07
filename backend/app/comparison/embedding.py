"""Fact embeddings for candidate search.

The text embedded is ``entity + attribute + qualifiers`` (§6.5), not the
evidence, so nearest neighbours are facts *about the same thing*, whatever their
values. Embeddings are always local.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fact import Fact
from app.providers import get_embedding_provider
from app.providers.base import EmbeddingProvider


def fact_embedding_text(entity: str, attribute: str, qualifiers: dict | None) -> str:
    parts = [entity.strip(), attribute.strip()]
    for key in sorted(qualifiers or {}):
        value = str((qualifiers or {})[key]).strip()
        if value:
            parts.append(f"{key}: {value}")
    return " | ".join(p for p in parts if p)


async def embed_missing_facts(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    provider: EmbeddingProvider | None = None,
    batch_size: int = 64,
) -> int:
    """Fill ``embedding`` for this project's facts that don't have one yet.
    Returns the number embedded."""
    provider = provider or get_embedding_provider()
    rows: Sequence[Fact] = (
        (
            await session.execute(
                select(Fact).where(Fact.project_id == project_id, Fact.embedding.is_(None))
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return 0

    for start in range(0, len(rows), batch_size):
        chunk = rows[start : start + batch_size]
        vectors = await provider.embed(
            [fact_embedding_text(f.entity, f.attribute, f.qualifiers) for f in chunk]
        )
        for fact, vector in zip(chunk, vectors, strict=True):
            fact.embedding = vector
    await session.flush()
    return len(rows)

"""The reasoning console's toolset: fact search (semantic + lexical) and
relationship lookup, all scoped to one project."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.fact import Fact
from app.models.relationship import FactRelationship
from app.providers import get_embedding_provider
from app.providers.base import EmbeddingProvider

TOOL_NAMES = ("search_facts", "get_relationships")

_USABLE = ("verified", "auto_corrected", "needs_review")


def format_quantitative_value(v: dict) -> str:
    """Render a quantitative value for display and for agent context.

    Found during review: the old ``v.get("comparator", "eq")`` default rendered
    inferred exact-equality for facts whose extractor never asserted a
    comparator. A missing/None comparator is now shown with a leading "~"
    (approximate); an explicit "eq" renders clean with no prefix.
    """
    comparator = v.get("comparator") or "unspecified"
    if comparator == "eq":
        prefix = ""
    elif comparator == "unspecified":
        prefix = "~"
    else:
        prefix = f"{comparator} "
    return f"{prefix}{v.get('number', '?')} {v.get('unit') or ''}".strip()


def summarize_fact(fact: Fact, doc_name: str | None = None) -> str:
    v = fact.value or {}
    if fact.fact_kind == "quantitative":
        val = format_quantitative_value(v)
    else:
        val = v.get("state") or v.get("text") or "?"
    period = (fact.period or {}).get("raw_label") or "-"
    where = f" ({doc_name}, p{fact.page_number})" if doc_name else ""
    return (
        f"{fact.entity} / {fact.attribute} = {val} [{period}]"
        f"{where} status={fact.verification_status}"
    )


@dataclass(slots=True)
class QueryTools:
    session: AsyncSession
    project_id: uuid.UUID
    embedder: EmbeddingProvider | None = None

    def _embedder(self) -> EmbeddingProvider:
        if self.embedder is None:
            self.embedder = get_embedding_provider()
        return self.embedder

    async def _doc_names(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not ids:
            return {}
        rows = (
            await self.session.execute(
                select(Document.document_id, Document.filename).where(Document.document_id.in_(ids))
            )
        ).all()
        return {r[0]: r[1] for r in rows}

    async def search_facts(
        self, query: str, *, fact_kind: str | None = None, limit: int = 8
    ) -> list[Fact]:
        """Semantic nearest-neighbour search over fact embeddings, with a lexical
        pass merged in so exact terms are never missed."""
        found: dict[uuid.UUID, Fact] = {}

        vector = (await self._embedder().embed([query]))[0]
        sem_stmt = (
            select(Fact)
            .where(
                Fact.project_id == self.project_id,
                Fact.verification_status.in_(_USABLE),
                Fact.embedding.is_not(None),
            )
            .order_by(Fact.embedding.cosine_distance(vector))
            .limit(limit)
        )
        if fact_kind:
            sem_stmt = sem_stmt.where(Fact.fact_kind == fact_kind)
        for f in (await self.session.execute(sem_stmt)).scalars().all():
            found[f.fact_id] = f

        like = f"%{query.strip()}%"
        lex_stmt = (
            select(Fact)
            .where(
                Fact.project_id == self.project_id,
                Fact.verification_status.in_(_USABLE),
                or_(
                    Fact.entity.ilike(like),
                    Fact.attribute.ilike(like),
                    Fact.evidence_text.ilike(like),
                ),
            )
            .limit(limit)
        )
        for f in (await self.session.execute(lex_stmt)).scalars().all():
            found.setdefault(f.fact_id, f)

        return list(found.values())

    async def get_relationships(self, fact_id: uuid.UUID) -> list[FactRelationship]:
        stmt = select(FactRelationship).where(
            FactRelationship.project_id == self.project_id,
            or_(
                FactRelationship.fact_a_id == fact_id,
                FactRelationship.fact_b_id == fact_id,
            ),
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def render_search(self, facts: list[Fact]) -> str:
        if not facts:
            return "(no matching facts)"
        names = await self._doc_names({f.document_id for f in facts})
        return "\n".join(
            f"- [{f.fact_id}] {summarize_fact(f, names.get(f.document_id, '?'))}" for f in facts
        )

    async def render_relationships(self, rels: list[FactRelationship]) -> str:
        if not rels:
            return "(no relationships)"
        return "\n".join(
            f"- {r.fact_a_id} <-{r.relationship_type}-> {r.fact_b_id}"
            f"{f' (basis: {r.reconciliation_basis})' if r.reconciliation_basis else ''}: "
            f"{r.explanation}"
            for r in rels
        )

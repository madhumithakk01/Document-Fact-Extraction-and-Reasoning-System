"""The fixed toolset for the reconciliation agent.

Three read-only lookups, all scoped to the project. Each returns a compact text
block for the model and is recorded verbatim in the investigation trail.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Chunk, Document
from app.models.fact import Fact

TOOL_NAMES = ("search_facts", "search_evidence_text", "get_surrounding_context")


def _fact_line(f: Fact, doc_name: str) -> str:
    v = f.value or {}
    if f.fact_kind == "quantitative":
        val = f"{v.get('comparator', 'eq')} {v.get('number', '?')} {v.get('unit') or ''}".strip()
    else:
        val = v.get("state") or v.get("text") or "?"
    period = (f.period or {}).get("raw_label") or "-"
    return (
        f"- [{f.fact_id}] {f.entity} / {f.attribute} = {val} [{period}] "
        f"({doc_name}, p{f.page_number}) status={f.verification_status}"
    )


@dataclass(slots=True)
class AgentTools:
    session: AsyncSession
    project_id: uuid.UUID

    async def _doc_names(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not ids:
            return {}
        rows = (
            await self.session.execute(
                select(Document.document_id, Document.filename).where(Document.document_id.in_(ids))
            )
        ).all()
        return {r[0]: r[1] for r in rows}

    async def search_facts(self, query: str, *, limit: int = 6) -> str:
        like = f"%{query.strip()}%"
        stmt = (
            select(Fact)
            .where(
                Fact.project_id == self.project_id,
                or_(
                    Fact.entity.ilike(like),
                    Fact.attribute.ilike(like),
                    Fact.evidence_text.ilike(like),
                ),
            )
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        if not rows:
            return f"search_facts({query!r}): no matching facts"
        names = await self._doc_names({r.document_id for r in rows})
        lines = [_fact_line(r, names.get(r.document_id, "?")) for r in rows]
        return f"search_facts({query!r}):\n" + "\n".join(lines)

    async def search_evidence_text(self, query: str, *, limit: int = 5) -> str:
        like = f"%{query.strip()}%"
        stmt = (
            select(Chunk, Document.filename)
            .join(Document, Document.document_id == Chunk.document_id)
            .where(Chunk.project_id == self.project_id, Chunk.text.ilike(like))
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        if not rows:
            return f"search_evidence_text({query!r}): no matching passages"
        out = [f"search_evidence_text({query!r}):"]
        for chunk, filename in rows:
            idx = chunk.text.lower().find(query.strip().lower())
            start = max(0, idx - 160)
            snippet = " ".join(chunk.text[start : idx + 200].split())
            out.append(f"- ({filename}, p{chunk.page_number}) ...{snippet}...")
        return "\n".join(out)

    async def get_surrounding_context(self, fact_id: str) -> str:
        try:
            fid = uuid.UUID(str(fact_id))
        except ValueError:
            return f"get_surrounding_context({fact_id!r}): not a valid fact id"
        fact = (
            await self.session.execute(
                select(Fact).where(Fact.project_id == self.project_id, Fact.fact_id == fid)
            )
        ).scalar_one_or_none()
        if fact is None:
            return f"get_surrounding_context({fact_id!r}): fact not found in this project"
        chunk = None
        if fact.chunk_id is not None:
            chunk = (
                await self.session.execute(select(Chunk).where(Chunk.chunk_id == fact.chunk_id))
            ).scalar_one_or_none()
        names = await self._doc_names({fact.document_id})
        header = (
            f"get_surrounding_context([{fact.fact_id}]) "
            f"({names.get(fact.document_id, '?')}, p{fact.page_number})"
        )
        if chunk is None:
            return f"{header}\nevidence: {fact.evidence_text}\n(no stored page text)"
        body = chunk.text if len(chunk.text) <= 1800 else chunk.text[:1800] + " ..."
        return f"{header}\nevidence: {fact.evidence_text}\n--- page text ---\n{body}"

    async def call(self, tool: str, *, query: str | None = None, fact_id: str | None = None) -> str:
        if tool == "search_facts":
            return await self.search_facts(query or "")
        if tool == "search_evidence_text":
            return await self.search_evidence_text(query or "")
        if tool == "get_surrounding_context":
            return await self.get_surrounding_context(fact_id or "")
        return f"unknown tool: {tool!r}"

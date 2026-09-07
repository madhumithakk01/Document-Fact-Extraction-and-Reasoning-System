"""Turn the gathered facts into a cited, disagreement-aware answer."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.fact import Fact
from app.models.relationship import FactRelationship
from app.providers.base import CompletionRequest, LLMProvider, ProviderError
from app.query.schema import Citation, Disagreement
from app.query.tools import summarize_fact

logger = logging.getLogger(__name__)

_DISPUTED_TYPES = ("contradicts", "reconciled_by_context")

_SYSTEM = """\
You answer a question using ONLY the numbered facts provided. Every claim in
your answer must carry an inline citation to the fact that supports it, written
as [F1], [F2], etc. Do not use any fact not in the list, and do not state
anything the facts do not.

If the facts include a disagreement (given to you under DISAGREEMENTS), you must
surface it in the answer as its own short sentence -- name both sides and their
citations -- rather than picking one side or averaging them. A reconciled
disagreement should be reported with the basis that reconciles it.

Keep the answer to a few sentences. If the facts do not address the question,
say so plainly.\
"""

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "string"},
        "cited_markers": {"type": "array", "items": {"type": "string"}},
        "surfaced_disagreements": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "marker_a": {"type": "string"},
                    "marker_b": {"type": "string"},
                },
                "required": ["marker_a", "marker_b"],
            },
        },
    },
    "required": ["answer", "cited_markers", "surfaced_disagreements"],
}


async def _load(
    session: AsyncSession, project_id: uuid.UUID, fact_ids: list[uuid.UUID]
) -> tuple[list[Fact], dict[uuid.UUID, str]]:
    if not fact_ids:
        return [], {}
    facts = (
        (
            await session.execute(
                select(Fact).where(Fact.project_id == project_id, Fact.fact_id.in_(fact_ids))
            )
        )
        .scalars()
        .all()
    )
    names = {
        r[0]: r[1]
        for r in (
            await session.execute(
                select(Document.document_id, Document.filename).where(
                    Document.document_id.in_({f.document_id for f in facts})
                )
            )
        ).all()
    }
    return list(facts), names


async def _relationships_among(
    session: AsyncSession, project_id: uuid.UUID, ids: set[uuid.UUID]
) -> list[FactRelationship]:
    if len(ids) < 2:
        return []
    rows = (
        (
            await session.execute(
                select(FactRelationship).where(
                    FactRelationship.project_id == project_id,
                    FactRelationship.relationship_type.in_(_DISPUTED_TYPES),
                    or_(
                        FactRelationship.fact_a_id.in_(ids),
                        FactRelationship.fact_b_id.in_(ids),
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    return [r for r in rows if r.fact_a_id in ids and r.fact_b_id in ids]


async def synthesize(
    session: AsyncSession,
    project_id: uuid.UUID,
    question: str,
    fact_ids: list[uuid.UUID],
    provider: LLMProvider,
) -> tuple[str, list[Citation], list[Disagreement]]:
    facts, names = await _load(session, project_id, fact_ids)
    if not facts:
        return (
            "This project has no verified facts that address that question.",
            [],
            [],
        )

    # order: quantitative first, then by entity, for stable markers
    facts.sort(key=lambda f: (f.fact_kind != "quantitative", f.entity.lower(), f.attribute.lower()))
    marker_of = {f.fact_id: f"F{i + 1}" for i, f in enumerate(facts)}
    by_marker = {v: k for k, v in marker_of.items()}
    fact_by_id = {f.fact_id: f for f in facts}

    fact_block = "\n".join(
        f"{marker_of[f.fact_id]}: {summarize_fact(f, names.get(f.document_id))}"
        f'  evidence: "{f.evidence_text}"'
        for f in facts
    )

    rels = await _relationships_among(session, project_id, set(fact_by_id))
    disagreement_block = (
        "\n".join(
            f"{marker_of[r.fact_a_id]} vs {marker_of[r.fact_b_id]}: {r.relationship_type}"
            f"{f' (basis: {r.reconciliation_basis})' if r.reconciliation_basis else ''} — "
            f"{r.explanation}"
            for r in rels
        )
        or "(none)"
    )

    user = f"QUESTION: {question}\n\nFACTS:\n{fact_block}\n\nDISAGREEMENTS:\n{disagreement_block}\n"
    try:
        result = await provider.complete(
            CompletionRequest(system=_SYSTEM, user=user, json_schema=_SCHEMA, temperature=0.0)
        )
        payload = result.json()
        if not isinstance(payload, dict):
            raise ProviderError("synthesis returned a non-object")
    except (ProviderError, ValueError) as exc:
        logger.warning("synthesis failed: %s", exc)
        return (
            "The answer could not be synthesised. The relevant facts are cited below.",
            _all_citations(facts, names, marker_of),
            _all_disagreements(rels, marker_of, fact_by_id, names),
        )

    answer = str(payload.get("answer") or "").strip()
    cited = {m for m in payload.get("cited_markers", []) if m in by_marker}
    # always include every fact actually referenced with [Fk] in the text
    for marker in by_marker:
        if f"[{marker}]" in answer:
            cited.add(marker)

    citations = [
        _citation(fact_by_id[by_marker[m]], names, m)
        for m in sorted(cited, key=lambda x: int(x[1:]))
    ]
    disagreements = _all_disagreements(rels, marker_of, fact_by_id, names)
    return answer, citations, disagreements


def _value_summary(f: Fact) -> str:
    v = f.value or {}
    if f.fact_kind == "quantitative":
        return f"{v.get('comparator', 'eq')} {v.get('number', '?')} {v.get('unit') or ''}".strip()
    return v.get("state") or v.get("text") or "?"


def _citation(f: Fact, names: dict[uuid.UUID, str], marker: str) -> Citation:
    return Citation(
        marker=marker,
        fact_id=str(f.fact_id),
        entity=f.entity,
        attribute=f.attribute,
        value_summary=_value_summary(f),
        period=(f.period or {}).get("raw_label"),
        verification_status=f.verification_status,
        document_filename=names.get(f.document_id, "document.pdf"),
        page_number=f.page_number,
        evidence_text=f.evidence_text,
    )


def _all_citations(
    facts: list[Fact], names: dict[uuid.UUID, str], marker_of: dict[uuid.UUID, str]
) -> list[Citation]:
    return [_citation(f, names, marker_of[f.fact_id]) for f in facts]


def _all_disagreements(
    rels: list[FactRelationship],
    marker_of: dict[uuid.UUID, str],
    fact_by_id: dict[uuid.UUID, Fact],
    names: dict[uuid.UUID, str],
) -> list[Disagreement]:
    out: list[Disagreement] = []
    for r in rels:
        fa, fb = fact_by_id[r.fact_a_id], fact_by_id[r.fact_b_id]
        out.append(
            Disagreement(
                relationship_type=r.relationship_type,
                reconciliation_basis=r.reconciliation_basis,
                explanation=r.explanation,
                marker_a=marker_of[r.fact_a_id],
                marker_b=marker_of[r.fact_b_id],
                fact_a_id=str(r.fact_a_id),
                fact_b_id=str(r.fact_b_id),
                fact_a_summary=summarize_fact(fa, names.get(fa.document_id)),
                fact_b_summary=summarize_fact(fb, names.get(fb.document_id)),
            )
        )
    return out

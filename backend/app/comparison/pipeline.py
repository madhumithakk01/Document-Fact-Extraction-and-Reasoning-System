"""Comparison pipeline: candidates -> pre-check -> adjudication -> reconciliation.

For each newly usable fact in a document, find its nearest neighbours in the
project, run the deterministic pre-check, and only fall through to a model call
when the pre-check cannot resolve it. Reconciliation runs only when adjudication
asks for more context. Every relationship is persisted with whatever trail was
produced.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.comparison.adjudicator import Adjudication, RelationshipType, adjudicate_pair
from app.comparison.candidates import _MAX_COSINE_DISTANCE, candidates_for_fact
from app.comparison.canonicalize import adjudicate_same_concept
from app.comparison.embedding import embed_missing_facts
from app.comparison.persist import persist_relationship, upsert_concept
from app.comparison.precheck import ComparableFact, PrecheckOutcome, deterministic_precheck
from app.comparison.reconciliation_agent import reconcile
from app.comparison.tools import AgentTools
from app.models.fact import Fact
from app.models.relationship import FactRelationship
from app.providers import get_embedding_provider, get_llm_provider
from app.providers.base import EmbeddingProvider, LLMProvider, ProviderError

logger = logging.getLogger(__name__)

_USABLE = ("verified", "auto_corrected")


@dataclass
class ComparisonStats:
    facts_considered: int = 0
    candidate_pairs: int = 0
    precheck_corroborates: int = 0
    precheck_not_comparable: int = 0
    adjudicated: int = 0
    reconciled: int = 0
    adjudication_errors: int = 0
    by_type: dict[str, int] = field(default_factory=dict)

    def record_type(self, t: str) -> None:
        self.by_type[t] = self.by_type.get(t, 0) + 1


@dataclass
class ComparisonResult:
    document_id: uuid.UUID
    relationships: list[FactRelationship]
    stats: ComparisonStats


def _comparable(fact: Fact) -> ComparableFact:
    return ComparableFact(
        fact_kind=fact.fact_kind,
        entity=fact.entity,
        attribute=fact.attribute,
        value=dict(fact.value or {}),
        period=dict(fact.period or {}),
        qualifiers=dict(fact.qualifiers or {}),
    )


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


class _ConceptResolver:
    """Resolves whether two entity/attribute strings are the same concept, once
    per pair, persisting confirmed merges as CanonicalConcept rows."""

    def __init__(self, session: AsyncSession, project_id: uuid.UUID, llm: LLMProvider) -> None:
        self._session = session
        self._project_id = project_id
        self._llm = llm
        self._cache: dict[tuple[str, frozenset[str]], str | None] = {}

    async def canonical(self, kind: str, a: str, b: str, doc_id: uuid.UUID | None) -> str | None:
        if _norm(a) == _norm(b):
            return a.strip()
        key = (kind, frozenset({_norm(a), _norm(b)}))
        if key in self._cache:
            return self._cache[key]
        decision = await adjudicate_same_concept(a, b, kind, self._llm)
        canonical = decision.canonical_name if decision.same_concept else None
        if decision.same_concept:
            await upsert_concept(
                self._session,
                self._project_id,
                kind=kind,
                canonical_name=decision.canonical_name,
                aliases=[a, b],
                first_seen_document_id=doc_id,
            )
        self._cache[key] = canonical
        return canonical


async def _resolve_concepts(
    resolver: _ConceptResolver, a: ComparableFact, b: ComparableFact, doc_id: uuid.UUID | None
) -> None:
    ent = await resolver.canonical("entity", a.entity, b.entity, doc_id)
    attr = await resolver.canonical("attribute", a.attribute, b.attribute, doc_id)
    if ent is not None:
        object.__setattr__(a, "canonical_entity", ent)
        object.__setattr__(b, "canonical_entity", ent)
    if attr is not None:
        object.__setattr__(a, "canonical_attribute", attr)
        object.__setattr__(b, "canonical_attribute", attr)


async def _existing_pairs(
    session: AsyncSession, project_id: uuid.UUID
) -> set[frozenset[uuid.UUID]]:
    rows = (
        await session.execute(
            select(FactRelationship.fact_a_id, FactRelationship.fact_b_id).where(
                FactRelationship.project_id == project_id
            )
        )
    ).all()
    return {frozenset((a, b)) for a, b in rows}


# An off-domain document forms a new sub-cluster of its own, so a full-strength
# project-wide search is wasted effort: only a capped, tight cross-cluster pass
# can surface a deliberate cross-domain link.
_CROSS_CLUSTER_K = 3
_CROSS_CLUSTER_MAX_DISTANCE = 0.30


async def compare_document(
    session: AsyncSession,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    llm: LLMProvider | None = None,
    embedder: EmbeddingProvider | None = None,
    k: int = 8,
    run_reconciliation: bool = True,
    off_domain: bool = False,
) -> ComparisonResult:
    llm = llm or get_llm_provider()
    embedder = embedder or get_embedding_provider()
    stats = ComparisonStats()

    cand_k = _CROSS_CLUSTER_K if off_domain else k
    cand_max_distance = _CROSS_CLUSTER_MAX_DISTANCE if off_domain else _MAX_COSINE_DISTANCE

    await embed_missing_facts(session, project_id, provider=embedder)

    new_facts = (
        (
            await session.execute(
                select(Fact).where(
                    Fact.project_id == project_id,
                    Fact.document_id == document_id,
                    Fact.verification_status.in_(_USABLE),
                )
            )
        )
        .scalars()
        .all()
    )

    seen = await _existing_pairs(session, project_id)
    tools = AgentTools(session=session, project_id=project_id)
    resolver = _ConceptResolver(session, project_id, llm)
    out: list[FactRelationship] = []

    for fact in new_facts:
        stats.facts_considered += 1
        candidates = await candidates_for_fact(
            session, project_id, fact, k=cand_k, max_distance=cand_max_distance
        )
        for cand in candidates:
            pair = frozenset((fact.fact_id, cand.fact.fact_id))
            if pair in seen:
                continue
            seen.add(pair)
            stats.candidate_pairs += 1

            a, b = _comparable(fact), _comparable(cand.fact)
            await _resolve_concepts(resolver, a, b, fact.document_id)
            pre = deterministic_precheck(a, b)

            if pre.outcome is PrecheckOutcome.corroborates:
                stats.precheck_corroborates += 1
                stats.record_type("corroborates")
                out.append(
                    await persist_relationship(
                        session,
                        project_id,
                        fact.fact_id,
                        cand.fact.fact_id,
                        relationship_type="corroborates",
                        explanation=pre.reason,
                        confidence=0.95,
                        investigation_trail=[
                            {"step": 0, "method": "deterministic_precheck", "detail": pre.detail}
                        ],
                    )
                )
                continue

            if pre.outcome is PrecheckOutcome.not_comparable:
                stats.precheck_not_comparable += 1
                continue

            # needs_adjudication -> model call
            try:
                adj = await adjudicate_pair(a, fact.evidence_text, b, cand.fact.evidence_text, llm)
                stats.adjudicated += 1
            except (ProviderError, ValueError) as exc:
                logger.warning(
                    "adjudication failed for %s/%s: %s", fact.fact_id, cand.fact.fact_id, exc
                )
                stats.adjudication_errors += 1
                continue

            trail: list = [{"step": 0, "method": "deterministic_precheck", "reason": pre.reason}]
            if run_reconciliation and adj.needs_more_context:
                rec = await reconcile(
                    a, fact.evidence_text, b, cand.fact.evidence_text, adj, tools, llm
                )
                adj = rec.adjudication
                trail.extend(rec.trail)
                stats.reconciled += 1

            if adj.relationship_type is RelationshipType.unrelated and not trail[1:]:
                continue  # nothing worth recording

            stats.record_type(adj.relationship_type.value)
            out.append(
                await persist_relationship(
                    session,
                    project_id,
                    fact.fact_id,
                    cand.fact.fact_id,
                    relationship_type=adj.relationship_type.value,
                    explanation=adj.explanation,
                    confidence=adj.confidence,
                    reconciliation_basis=adj.reconciliation_basis,
                    investigation_trail=trail,
                )
            )

    logger.info(
        "compared %s: %d pairs -> %s",
        document_id,
        stats.candidate_pairs,
        dict(stats.by_type),
    )
    return ComparisonResult(document_id=document_id, relationships=out, stats=stats)


async def compare_pair(a: Fact, b: Fact, *, llm: LLMProvider | None = None) -> Adjudication:
    """Adjudicate two already-loaded facts directly (no candidate search)."""
    llm = llm or get_llm_provider()
    return await adjudicate_pair(
        _comparable(a), a.evidence_text, _comparable(b), b.evidence_text, llm
    )

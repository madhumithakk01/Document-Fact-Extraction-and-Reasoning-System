"""Comparison: deterministic pre-check, embedding candidates, adjudication, and
the bounded reconciliation agent.

:func:`deterministic_precheck` resolves only what it can be certain of --
``corroborates``. Everything else goes to :func:`adjudicate_pair`, which
classifies as corroborates / contradicts / reconciled_by_context / unrelated and
never picks a side between two disagreeing sources. When adjudication asks for
more context, :func:`reconcile` runs a fixed toolset with a hard cap of three
calls, logging every one to the investigation trail before forcing a final
classification.
"""

from app.comparison.adjudicator import Adjudication, RelationshipType, adjudicate_pair
from app.comparison.candidates import Candidate, candidates_for_fact
from app.comparison.canonicalize import ConceptDecision, adjudicate_same_concept
from app.comparison.embedding import embed_missing_facts, fact_embedding_text
from app.comparison.pipeline import (
    ComparisonResult,
    ComparisonStats,
    compare_document,
    compare_pair,
)
from app.comparison.precheck import (
    ComparableFact,
    PrecheckOutcome,
    PrecheckResult,
    deterministic_precheck,
)
from app.comparison.reconciliation_agent import ReconciliationResult, reconcile
from app.comparison.tools import AgentTools

__all__ = [
    "Adjudication",
    "AgentTools",
    "Candidate",
    "ComparableFact",
    "ComparisonResult",
    "ComparisonStats",
    "ConceptDecision",
    "PrecheckOutcome",
    "PrecheckResult",
    "ReconciliationResult",
    "RelationshipType",
    "adjudicate_pair",
    "adjudicate_same_concept",
    "candidates_for_fact",
    "compare_document",
    "compare_pair",
    "deterministic_precheck",
    "embed_missing_facts",
    "fact_embedding_text",
    "reconcile",
]

"""Live comparison pipeline: candidates -> pre-check -> adjudication -> persist.

Uses the real database and the real local embedder; the LLM is scripted so the
adjudication and reconciliation branches are exercised deterministically.
"""

from __future__ import annotations

import json

import pytest

from app.comparison.pipeline import compare_document
from app.providers.base import CompletionRequest, CompletionResult, LLMProvider
from app.repository import create_project, delete_project, list_relationships
from app.repository.scope import ProjectScope
from tests.comparison.conftest import make_document, make_fact

pytestmark = pytest.mark.slow


class ScriptedLLM(LLMProvider):
    name = "scripted"

    def __init__(self, adjudication: dict) -> None:
        self.adjudication = adjudication
        self.calls = 0

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.calls += 1
        return CompletionResult(text=json.dumps(self.adjudication), model="m", provider="scripted")

    async def health_check(self) -> bool:
        return True


def _adj(rt: str, basis: str | None = None) -> dict:
    return {
        "entity_match": True,
        "attribute_match": True,
        "period_relation": "same",
        "unit_scale_note": "scaled and compared",
        "qualifier_explanation": "basis differs",
        "comparator_consistent": True,
        "relationship_type": rt,
        "reconciliation_basis": basis,
        "explanation": "scripted verdict",
        "confidence": 0.8,
        "needs_more_context": False,
        "missing_context": None,
    }


async def test_deterministic_corroboration_and_adjudicated_reconcile(db_session) -> None:
    proj = await create_project(db_session, "cmp-pipeline")
    llm = ScriptedLLM(_adj("reconciled_by_context", basis="standalone vs consolidated"))
    try:
        doc_a = make_document(proj.project_id, "annual-report.pdf")
        doc_b = make_document(proj.project_id, "earnings-deck.pdf")
        db_session.add_all([doc_a, doc_b])
        await db_session.flush()

        # corroborating pair, resolvable with zero model calls (Cr vs million)
        f1 = make_fact(
            proj.project_id,
            doc_a.document_id,
            entity="Delhivery",
            attribute="FY24 consolidated EBITDA",
            value={"comparator": "eq", "number": 127, "unit": "INR Crore"},
            period="FY24",
            qualifiers={"basis": "consolidated"},
            evidence="FY24 consolidated EBITDA was INR 127 Cr",
        )
        f2 = make_fact(
            proj.project_id,
            doc_b.document_id,
            entity="Delhivery",
            attribute="FY24 EBITDA consolidated",
            value={"comparator": "eq", "number": 1266.41, "unit": "INR million"},
            period="FY 2023-24",
            qualifiers={"basis": "consolidated"},
            evidence="EBITDA / EBITDA margin Rs.1,266.41 million",
        )
        # same subject/attribute/period, differing significant qualifier -> adjudication
        f3 = make_fact(
            proj.project_id,
            doc_b.document_id,
            entity="Delhivery",
            attribute="FY24 consolidated EBITDA",
            value={"comparator": "eq", "number": 200, "unit": "INR Crore"},
            period="FY24",
            qualifiers={"basis": "standalone"},
            evidence="standalone EBITDA of INR 200 Cr",
        )
        db_session.add_all([f1, f2, f3])
        await db_session.flush()

        result = await compare_document(db_session, proj.project_id, doc_b.document_id, llm=llm)

        by_type = result.stats.by_type
        assert by_type.get("corroborates", 0) >= 1
        assert by_type.get("reconciled_by_context", 0) >= 1
        assert result.stats.precheck_corroborates >= 1  # f2 <-> f1 with no model call
        assert llm.calls >= 1  # f3 <-> f1 went to adjudication

        scope = ProjectScope(project_id=proj.project_id, session=db_session)
        rels = await list_relationships(scope)
        kinds = {r.relationship_type for r in rels}
        assert "corroborates" in kinds
        assert "reconciled_by_context" in kinds

        corr = next(r for r in rels if r.relationship_type == "corroborates")
        assert corr.investigation_trail[0]["method"] == "deterministic_precheck"
        rec = next(r for r in rels if r.relationship_type == "reconciled_by_context")
        assert rec.reconciliation_basis == "standalone vs consolidated"
    finally:
        await db_session.rollback()
        await delete_project(db_session, proj.project_id)
        await db_session.commit()

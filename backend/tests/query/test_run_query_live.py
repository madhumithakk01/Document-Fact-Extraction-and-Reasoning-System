"""Phase 10 exit criterion: an open question gets a cited answer, and a genuine
underlying disagreement is surfaced rather than hidden.

Live database, scripted LLM (both the gathering steps and the synthesis).
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.comparison.embedding import embed_missing_facts
from app.comparison.persist import persist_relationship
from app.config import get_settings
from app.providers.base import CompletionRequest, CompletionResult, LLMProvider
from app.query import run_query
from app.query.agent import _SYSTEM as GATHER_SYSTEM
from app.repository import create_project, delete_project
from tests._env import db_reachable
from tests.comparison.conftest import make_document, make_fact

pytestmark = [pytest.mark.slow, pytest.mark.skipif(not db_reachable(), reason="no database")]


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
    await engine.dispose()


class ScriptedLLM(LLMProvider):
    """Answers the gathering steps from ``steps``; every other call is the
    synthesis, answered with ``synthesis``."""

    name = "scripted"

    def __init__(self, steps: list[dict], synthesis: dict) -> None:
        self.steps = list(steps)
        self.synthesis = synthesis

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        if request.system.startswith(GATHER_SYSTEM[:40]):
            item = (
                self.steps.pop(0)
                if self.steps
                else {
                    "action": "conclude",
                    "query": None,
                    "fact_kind": None,
                    "fact_id": None,
                    "rationale": "done",
                }
            )
            return CompletionResult(text=json.dumps(item), model="m", provider="scripted")
        return CompletionResult(text=json.dumps(self.synthesis), model="m", provider="scripted")

    async def health_check(self) -> bool:
        return True


async def test_answer_is_cited_and_the_disagreement_is_surfaced(session: AsyncSession) -> None:
    project = await create_project(session, "reasoning-console-test")
    pid = project.project_id
    try:
        d_rbi = make_document(pid, "rbi-annual-report.pdf")
        d_imf = make_document(pid, "imf-article-iv.pdf")
        session.add_all([d_rbi, d_imf])
        await session.flush()

        f_rbi = make_fact(
            pid,
            d_rbi.document_id,
            entity="India",
            attribute="real GDP growth",
            value={"comparator": "eq", "number": 6.5, "unit": "%"},
            period="2025-26",
            evidence="real GDP growth for 2025-26 is projected at 6.5 per cent",
            page=42,
        )
        f_imf = make_fact(
            pid,
            d_imf.document_id,
            entity="India",
            attribute="real GDP growth",
            value={"comparator": "eq", "number": 6.6, "unit": "%"},
            period="FY2025/26",
            evidence="staff project real GDP growth at 6.6 percent",
            page=7,
        )
        session.add_all([f_rbi, f_imf])
        await session.flush()
        await embed_missing_facts(session, pid)

        await persist_relationship(
            session,
            pid,
            f_rbi.fact_id,
            f_imf.fact_id,
            relationship_type="contradicts",
            explanation="RBI projects 6.5% while the IMF projects 6.6% for the same year, "
            "with no differing basis.",
            confidence=0.8,
        )
        await session.commit()

        scripted = ScriptedLLM(
            steps=[
                {
                    "action": "search_facts",
                    "query": "India real GDP growth 2025-26",
                    "fact_kind": None,
                    "fact_id": None,
                    "rationale": "core facts",
                },
                {
                    "action": "conclude",
                    "query": None,
                    "fact_kind": None,
                    "fact_id": None,
                    "rationale": "have both projections",
                },
            ],
            synthesis={
                "answer": "Projections for India's FY2025-26 real GDP growth differ: the RBI "
                "puts it at 6.5% [F1] while the IMF puts it at 6.6% [F2]. These two sources "
                "disagree and nothing in the facts reconciles the gap.",
                "cited_markers": ["F1", "F2"],
                "surfaced_disagreements": [{"marker_a": "F1", "marker_b": "F2"}],
            },
        )

        result = await run_query(
            session, pid, "What is India's projected GDP growth for 2025-26?", llm=scripted
        )

        assert "[F1]" in result.answer and "[F2]" in result.answer
        assert {c.marker for c in result.citations} == {"F1", "F2"}
        assert {c.fact_id for c in result.citations} == {str(f_rbi.fact_id), str(f_imf.fact_id)}
        assert len(result.disagreements) == 1
        d = result.disagreements[0]
        assert d.relationship_type == "contradicts"
        assert {d.fact_a_id, d.fact_b_id} == {str(f_rbi.fact_id), str(f_imf.fact_id)}
        assert result.tool_calls_used == 1
        assert any(t.tool == "search_facts" for t in result.trace)
        # a citation carries enough to open the evidence panel
        c = result.citations[0]
        assert c.document_filename.endswith(".pdf")
        assert c.page_number in (42, 7)
        assert c.evidence_text
    finally:
        await session.rollback()
        await delete_project(session, pid)
        await session.commit()


async def test_no_relevant_facts_answers_plainly(session: AsyncSession) -> None:
    project = await create_project(session, "reasoning-empty")
    pid = project.project_id
    try:
        scripted = ScriptedLLM(
            steps=[], synthesis={"answer": "x", "cited_markers": [], "surfaced_disagreements": []}
        )
        result = await run_query(session, pid, "anything?", llm=scripted)
        assert result.citations == []
        assert "no verified facts" in result.answer.lower()
    finally:
        await delete_project(session, pid)
        await session.commit()

"""Run a question end to end: gather -> synthesise."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.providers import get_embedding_provider, get_llm_provider
from app.providers.base import EmbeddingProvider, LLMProvider
from app.query.agent import gather
from app.query.schema import QueryResult
from app.query.synthesis import synthesize
from app.query.tools import QueryTools

logger = logging.getLogger(__name__)


async def run_query(
    session: AsyncSession,
    project_id: uuid.UUID,
    question: str,
    *,
    llm: LLMProvider | None = None,
    embedder: EmbeddingProvider | None = None,
    max_steps: int = 5,
) -> QueryResult:
    llm = llm or get_llm_provider()
    embedder = embedder or get_embedding_provider()
    tools = QueryTools(session=session, project_id=project_id, embedder=embedder)

    fact_ids, trace, used = await gather(question, tools, llm, max_steps=max_steps)
    answer, citations, disagreements = await synthesize(
        session, project_id, question, fact_ids, llm
    )

    logger.info(
        "query answered for project %s: %d fact(s) gathered in %d tool call(s), "
        "%d citation(s), %d disagreement(s)",
        project_id,
        len(fact_ids),
        used,
        len(citations),
        len(disagreements),
    )
    return QueryResult(
        question=question,
        answer=answer,
        citations=citations,
        disagreements=disagreements,
        trace=trace,
        fact_ids_considered=[str(f) for f in fact_ids],
        tool_calls_used=used,
    )

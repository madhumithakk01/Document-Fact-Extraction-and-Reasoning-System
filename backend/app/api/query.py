"""Reasoning-console endpoint: an open question -> a cited, disagreement-aware answer."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import project_scope
from app.api.schemas import QueryRequest
from app.query import QueryResult, run_query
from app.repository.scope import ProjectScope

router = APIRouter(prefix="/projects/{project_id}/query", tags=["query"])


@router.post("", response_model=QueryResult)
async def ask(body: QueryRequest, scope: ProjectScope = Depends(project_scope)) -> QueryResult:
    return await run_query(scope.session, scope.project_id, body.question.strip())

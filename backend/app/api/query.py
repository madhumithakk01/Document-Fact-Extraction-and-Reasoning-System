"""Reasoning-console endpoint.

The bounded query agent is built in a later phase; the route exists so the API
surface is complete and returns a clear 501 until then.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import project_scope
from app.api.schemas import QueryRequest
from app.repository.scope import ProjectScope

router = APIRouter(prefix="/projects/{project_id}/query", tags=["query"])


@router.post("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def ask(body: QueryRequest, scope: ProjectScope = Depends(project_scope)) -> dict:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="the reasoning console is not enabled yet",
    )

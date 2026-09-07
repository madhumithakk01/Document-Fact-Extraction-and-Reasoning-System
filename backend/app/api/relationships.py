"""Relationship endpoints: filtered list and detail with both facts."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import project_scope
from app.api.schemas import FactOut, RelationshipDetail, RelationshipOut
from app.models.constants import RELATIONSHIP_TYPES
from app.repository import get_fact, get_relationship, list_relationships
from app.repository.scope import ProjectScope

router = APIRouter(prefix="/projects/{project_id}/relationships", tags=["relationships"])


@router.get("", response_model=list[RelationshipOut])
async def index(
    scope: ProjectScope = Depends(project_scope),
    type: str | None = Query(None, alias="type"),
    min_confidence: float | None = Query(None, ge=0, le=1),
    fact_id: uuid.UUID | None = None,
) -> list[RelationshipOut]:
    if type is not None and type not in RELATIONSHIP_TYPES:
        raise HTTPException(status_code=400, detail=f"unknown relationship type {type!r}")
    rels = await list_relationships(
        scope, relationship_type=type, min_confidence=min_confidence, fact_id=fact_id
    )
    return [RelationshipOut.of(r) for r in rels]


@router.get("/{relationship_id}", response_model=RelationshipDetail)
async def show(
    relationship_id: uuid.UUID, scope: ProjectScope = Depends(project_scope)
) -> RelationshipDetail:
    rel = await get_relationship(scope, relationship_id)
    if rel is None:
        raise HTTPException(status_code=404, detail=f"relationship {relationship_id} not found")
    fact_a = await get_fact(scope, rel.fact_a_id)
    fact_b = await get_fact(scope, rel.fact_b_id)
    if fact_a is None or fact_b is None:
        raise HTTPException(status_code=404, detail="one of the related facts no longer exists")
    return RelationshipDetail(
        **RelationshipOut.of(rel).model_dump(),
        fact_a=FactOut.of(fact_a),
        fact_b=FactOut.of(fact_b),
    )

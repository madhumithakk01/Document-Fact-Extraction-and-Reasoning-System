"""Project endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.api.schemas import ProjectCreate, ProjectOut, ProjectSummary
from app.models.concept import CanonicalConcept
from app.models.document import Document
from app.models.fact import Fact
from app.models.relationship import FactRelationship
from app.repository import create_project, get_project, list_projects

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create(body: ProjectCreate, session: AsyncSession = Depends(db_session)) -> ProjectOut:
    project = await create_project(session, body.name)
    return ProjectOut.of(project)


@router.get("", response_model=list[ProjectOut])
async def index(session: AsyncSession = Depends(db_session)) -> list[ProjectOut]:
    return [ProjectOut.of(p) for p in await list_projects(session)]


async def _counts(session: AsyncSession, table, column, project_id: uuid.UUID) -> dict[str, int]:
    rows = (
        await session.execute(
            select(column, func.count()).where(table.project_id == project_id).group_by(column)
        )
    ).all()
    return {str(k): int(n) for k, n in rows}


@router.get("/{project_id}", response_model=ProjectSummary)
async def show(
    project_id: uuid.UUID, session: AsyncSession = Depends(db_session)
) -> ProjectSummary:
    project = await get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"project {project_id} not found")

    async def _n(table) -> int:
        return int(
            await session.scalar(
                select(func.count()).select_from(table).where(table.project_id == project_id)
            )
        )

    return ProjectSummary(
        **ProjectOut.of(project).model_dump(),
        document_count=await _n(Document),
        fact_count=await _n(Fact),
        facts_by_status=await _counts(session, Fact, Fact.verification_status, project_id),
        relationship_count=await _n(FactRelationship),
        relationships_by_type=await _counts(
            session, FactRelationship, FactRelationship.relationship_type, project_id
        ),
        concept_count=await _n(CanonicalConcept),
        sub_cluster_count=len((project.domain_profile or {}).get("sub_clusters", [])),
    )

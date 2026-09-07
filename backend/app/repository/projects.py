"""Project lifecycle. These are the only functions that operate without an
existing :class:`ProjectScope`, because they create or enumerate the boundary
itself."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import EMPTY_DOMAIN_PROFILE, Project


async def create_project(session: AsyncSession, name: str) -> Project:
    project = Project(
        project_id=uuid.uuid4(),
        name=name.strip(),
        domain_profile=dict(EMPTY_DOMAIN_PROFILE),
    )
    session.add(project)
    await session.flush()
    return project


async def get_project(session: AsyncSession, project_id: uuid.UUID) -> Project | None:
    return await session.get(Project, project_id)


async def list_projects(session: AsyncSession) -> Sequence[Project]:
    result = await session.execute(select(Project).order_by(Project.created_at.desc()))
    return result.scalars().all()


async def delete_project(session: AsyncSession, project_id: uuid.UUID) -> bool:
    project = await session.get(Project, project_id)
    if project is None:
        return False
    await session.delete(project)  # ON DELETE CASCADE removes everything under it
    await session.flush()
    return True

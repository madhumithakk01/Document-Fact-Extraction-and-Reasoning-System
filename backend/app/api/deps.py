"""Shared FastAPI dependencies: DB session and the project scope.

Every ``/projects/{project_id}/...`` route depends on ``project_scope``, which
404s if the project does not exist and otherwise hands the handler a
:class:`ProjectScope` bound to that one project. Handlers use the repository, so
no query can address another project's data.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionFactory
from app.repository import get_project
from app.repository.scope import ProjectScope


async def db_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def project_scope(
    project_id: uuid.UUID = Path(...),
    session: AsyncSession = Depends(db_session),
) -> ProjectScope:
    if await get_project(session, project_id) is None:
        raise HTTPException(status_code=404, detail=f"project {project_id} not found")
    return ProjectScope(project_id=project_id, session=session)

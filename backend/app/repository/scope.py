"""The project scope and the single entry point for building scoped queries."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class ProjectScope:
    """Carries the project boundary for a unit of work. Constructed once, from
    the ``project_id`` in the request path, and threaded through every call."""

    project_id: uuid.UUID
    session: AsyncSession

    def __post_init__(self) -> None:
        if not isinstance(self.project_id, uuid.UUID):
            raise TypeError("ProjectScope.project_id must be a uuid.UUID")


def scoped_select(model: Any, scope: ProjectScope, *extra_where: Any) -> Select:
    """Start a SELECT already filtered to the scope's project.

    Every read in this package goes through here, so ``project_id`` is always
    the first predicate and can never be forgotten. ``model`` must expose a
    ``project_id`` column.
    """
    if not hasattr(model, "project_id"):
        raise TypeError(f"{model!r} has no project_id column; it cannot be project-scoped")
    stmt = select(model).where(model.project_id == scope.project_id)
    for clause in extra_where:
        stmt = stmt.where(clause)
    return stmt

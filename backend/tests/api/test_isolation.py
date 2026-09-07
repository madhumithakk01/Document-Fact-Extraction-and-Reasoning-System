"""Project isolation over HTTP: one project's ids are invisible through another's URL."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.repository import create_project, delete_project
from tests.api.conftest import requires_db
from tests.comparison.conftest import make_document, make_fact

pytestmark = [pytest.mark.slow, requires_db]


async def _seed_fact_in_new_project(name: str) -> tuple[uuid.UUID, uuid.UUID]:
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        p = await create_project(s, name)
        d = make_document(p.project_id)
        s.add(d)
        await s.flush()
        f = make_fact(
            p.project_id,
            d.document_id,
            entity="X",
            attribute="y",
            value={"comparator": "eq", "number": 1},
            period="FY24",
        )
        s.add(f)
        await s.commit()
        pid, fid = p.project_id, f.fact_id
    await engine.dispose()
    return pid, fid


async def _drop(project_id: uuid.UUID) -> None:
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await delete_project(s, project_id)
        await s.commit()
    await engine.dispose()


def test_fact_from_one_project_is_404_through_another_projects_url(client) -> None:
    pid_a, fact_a = asyncio.run(_seed_fact_in_new_project("iso-a"))
    pid_b = uuid.UUID(client.post("/projects", json={"name": "iso-b"}).json()["project_id"])
    try:
        assert client.get(f"/projects/{pid_a}/facts/{fact_a}").status_code == 200
        assert client.get(f"/projects/{pid_b}/facts/{fact_a}").status_code == 404
        assert client.get(f"/projects/{pid_a}/facts").json()
        assert client.get(f"/projects/{pid_b}/facts").json() == []
    finally:
        asyncio.run(_drop(pid_a))
        asyncio.run(_drop(pid_b))

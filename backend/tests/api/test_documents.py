from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.pipeline_task import _budget_seconds
from app.config import get_settings
from app.repository import create_project, delete_project
from tests.api.conftest import requires_db
from tests.comparison.conftest import make_document


def test_budget_seconds_has_a_floor_and_scales_with_pages() -> None:
    assert _budget_seconds(0) == 600.0
    assert _budget_seconds(10) == 600.0  # still under the floor
    assert _budget_seconds(100) == 800.0
    assert _budget_seconds(1000) == 8000.0


async def _seed_document(status: str) -> tuple[uuid.UUID, uuid.UUID]:
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        project = await create_project(s, f"doc-retry-{status}-{uuid.uuid4().hex[:6]}")
        doc = make_document(project.project_id)
        doc.processing_status = status
        doc.processing_error = "boom" if status == "failed" else None
        s.add(doc)
        await s.commit()
        ids = (project.project_id, doc.document_id)
    await engine.dispose()
    return ids


async def _drop_project(project_id: uuid.UUID) -> None:
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await delete_project(s, project_id)
        await s.commit()
    await engine.dispose()


@pytest.mark.slow
@requires_db
def test_retry_requeues_a_failed_document_and_rejects_the_rest(client) -> None:
    pid_failed, did_failed = asyncio.run(_seed_document("failed"))
    pid_ready, did_ready = asyncio.run(_seed_document("ready"))
    try:
        r = client.post(f"/projects/{pid_failed}/documents/{did_failed}/retry")
        assert r.status_code == 202
        body = r.json()
        assert body["processing_status"] == "queued"
        assert body["processing_error"] is None

        # a document that never failed cannot be retried
        assert (
            client.post(f"/projects/{pid_ready}/documents/{did_ready}/retry").status_code == 409
        )
        # unknown document id is a 404
        assert (
            client.post(f"/projects/{pid_failed}/documents/{uuid.uuid4()}/retry").status_code
            == 404
        )
    finally:
        asyncio.run(_drop_project(pid_failed))
        asyncio.run(_drop_project(pid_ready))

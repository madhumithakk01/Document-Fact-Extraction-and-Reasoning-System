"""The pre-processed snapshot loads into a fresh database so the app opens
populated (BUILD_PHASES §12)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.concept import CanonicalConcept
from app.models.document import Document
from app.models.fact import Fact
from app.models.project import Project
from app.models.relationship import FactRelationship
from app.repository import delete_project
from scripts.seed import SNAPSHOT_PATH, _insert_project
from tests._env import db_reachable

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not SNAPSHOT_PATH.is_file(), reason="no seed snapshot"),
    pytest.mark.skipif(not db_reachable(), reason="no database"),
]


def test_snapshot_file_is_well_formed() -> None:
    data = json.loads(Path(SNAPSHOT_PATH).read_text(encoding="utf-8"))
    assert {p["name"] for p in data["projects"]} == {"delhivery-filings", "india-macroeconomy"}
    for proj in data["projects"]:
        doc_refs = {d["ref"] for d in proj["documents"]}
        fact_refs = {f["ref"] for f in proj["facts"]}
        assert proj["facts"], f"{proj['name']} has no facts"
        for f in proj["facts"]:
            assert f["document_ref"] in doc_refs
            assert f["evidence_text"].strip()
        for r in proj["relationships"]:
            assert r["fact_a_ref"] in fact_refs and r["fact_b_ref"] in fact_refs
            assert r["relationship_type"] in (
                "corroborates",
                "contradicts",
                "reconciled_by_context",
                "unrelated",
            )


async def test_snapshot_loads_into_a_fresh_database() -> None:
    data = json.loads(Path(SNAPSHOT_PATH).read_text(encoding="utf-8"))
    engine = create_async_engine(get_settings().database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    created: list = []
    try:
        async with maker() as s:
            for proj in data["projects"]:
                renamed = {**proj, "name": f"__seedtest__{proj['name']}"}
                await _insert_project(s, renamed)
            await s.commit()

        async with maker() as s:
            rows = (
                (await s.execute(select(Project).where(Project.name.like("__seedtest__%"))))
                .scalars()
                .all()
            )
            created = [p.project_id for p in rows]
            assert len(created) == 2

            for proj_json, project in zip(
                sorted(data["projects"], key=lambda p: p["name"]),
                sorted(rows, key=lambda p: p.name),
                strict=True,
            ):
                pid = project.project_id
                n_docs = await s.scalar(
                    select(func.count()).select_from(Document).where(Document.project_id == pid)
                )
                n_facts = await s.scalar(
                    select(func.count()).select_from(Fact).where(Fact.project_id == pid)
                )
                n_rels = await s.scalar(
                    select(func.count())
                    .select_from(FactRelationship)
                    .where(FactRelationship.project_id == pid)
                )
                n_concepts = await s.scalar(
                    select(func.count())
                    .select_from(CanonicalConcept)
                    .where(CanonicalConcept.project_id == pid)
                )
                assert n_docs == len(proj_json["documents"])
                assert n_facts == len(proj_json["facts"])
                assert n_rels == len(proj_json["relationships"])
                assert n_concepts == len(proj_json["concepts"])

            # at least one project has a resolved disagreement to demo
            all_types = (
                (
                    await s.execute(
                        select(FactRelationship.relationship_type).where(
                            FactRelationship.project_id.in_(created)
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert "corroborates" in all_types
            assert "reconciled_by_context" in all_types
    finally:
        async with maker() as s:
            for pid in created:
                await delete_project(s, pid)
            await s.commit()
        await engine.dispose()

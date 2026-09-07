"""Seed the database with a pre-processed snapshot of the starter documents so
the app opens populated.

    python -m scripts.seed load                 # fast: load seed/snapshot.json
    python -m scripts.seed build                # slow: regenerate the snapshot
    python -m scripts.seed build --full         # ... over every page (very slow)

``load`` needs only the database. ``build`` runs the real pipeline and needs a
provider (GROQ_API_KEY or Ollama) and the datasets/ directory.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.concept import CanonicalConcept
from app.models.document import Chunk, Document
from app.models.fact import Fact
from app.models.project import Project
from app.models.relationship import FactRelationship

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "seed" / "snapshot.json"
DATASETS = Path(__file__).resolve().parents[2] / "datasets"

# (project name, [(relative pdf path, pages-to-process or None for all)])
_PLAN: dict[str, list[tuple[str, list[int] | None]]] = {
    "delhivery-filings": [
        ("delhivery/03-delhivery-q4-fy24-earnings-presentation.pdf", [5, 6]),
        ("delhivery/02-delhivery-annual-report-fy24-excerpt.pdf", [6, 69]),
        ("delhivery/01-delhivery-prospectus-2022-excerpt.pdf", [4]),
    ],
    "india-macroeconomy": [
        ("india-macroeconomy/03-imf-india-2025-article-iv-excerpt.pdf", [4, 5]),
        ("india-macroeconomy/02-rbi-annual-report-2024-25-excerpt.pdf", [11, 12]),
        ("india-macroeconomy/01-india-economic-survey-2024-25-excerpt.pdf", [5, 6]),
    ],
}


def _engine():  # type: ignore[no-untyped-def]
    return create_async_engine(get_settings().database_url)


# --------------------------------------------------------------------------- load
async def _load() -> int:
    if not SNAPSHOT_PATH.is_file():
        print(f"no snapshot at {SNAPSHOT_PATH}; run `build` first", file=sys.stderr)
        return 2
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    engine = _engine()
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        for proj in snapshot["projects"]:
            existing = (
                await session.execute(select(Project).where(Project.name == proj["name"]))
            ).scalar_one_or_none()
            if existing is not None:
                print(f"project {proj['name']!r} already present; skipping")
                continue
            await _insert_project(session, proj)
        await session.commit()
    await engine.dispose()

    n = sum(len(p["facts"]) for p in snapshot["projects"])
    print(f"loaded {len(snapshot['projects'])} project(s), {n} fact(s)")
    return 0


async def _insert_project(session: Any, proj: dict) -> None:
    pid = uuid.uuid4()
    session.add(
        Project(project_id=pid, name=proj["name"], domain_profile=proj.get("domain_profile", {}))
    )
    await session.flush()  # FKs are checked at insert time
    doc_id_map: dict[str, uuid.UUID] = {}
    for d in proj["documents"]:
        new_id = uuid.uuid4()
        doc_id_map[d["ref"]] = new_id
        session.add(
            Document(
                document_id=new_id,
                project_id=pid,
                filename=d["filename"],
                content_hash=d["content_hash"],
                byte_size=d["byte_size"],
                content_type_detected=d["content_type_detected"],
                processing_status="ready",
                page_count=d["page_count"],
                ocr_page_count=d.get("ocr_page_count", 0),
                routing_profile=d.get("routing_profile", {}),
                sub_cluster_id=d.get("sub_cluster_id"),
                off_domain=d.get("off_domain", False),
            )
        )
    await session.flush()  # documents before chunks/facts/concepts
    chunk_id_map: dict[str, uuid.UUID] = {}
    for c in proj.get("chunks", []):
        new_id = uuid.uuid4()
        chunk_id_map[c["ref"]] = new_id
        session.add(
            Chunk(
                chunk_id=new_id,
                document_id=doc_id_map[c["document_ref"]],
                project_id=pid,
                chunk_index=c["chunk_index"],
                page_number=c["page_number"],
                text=c["text"],
                leading_context=c.get("leading_context", ""),
                char_start=c.get("char_start", 0),
                char_end=c.get("char_end", 0),
                content_type=c["content_type"],
                has_table=c.get("has_table", False),
                table_markdown=c.get("table_markdown"),
                page_image_ref=c.get("page_image_ref"),
                confidence_ceiling=c.get("confidence_ceiling", 1.0),
            )
        )
    await session.flush()  # chunks before facts
    fact_id_map: dict[str, uuid.UUID] = {}
    for f in proj["facts"]:
        new_id = uuid.uuid4()
        fact_id_map[f["ref"]] = new_id
        session.add(
            Fact(
                fact_id=new_id,
                project_id=pid,
                document_id=doc_id_map[f["document_ref"]],
                chunk_id=chunk_id_map.get(f.get("chunk_ref", "")),
                source_anchor=f.get("source_anchor", {}),
                page_number=f.get("page_number"),
                fact_kind=f["fact_kind"],
                entity=f["entity"],
                entity_resolved=f.get("entity_resolved", True),
                attribute=f["attribute"],
                value=f.get("value", {}),
                period=f.get("period", {}),
                qualifiers=f.get("qualifiers", {}),
                evidence_text=f["evidence_text"],
                verification_status=f.get("verification_status", "verified"),
                extraction_confidence=f.get("extraction_confidence", 0.8),
                verifier_confidence=f.get("verifier_confidence"),
                notes=f.get("notes", []),
            )
        )
    await session.flush()  # facts before relationships
    for r in proj.get("relationships", []):
        session.add(
            FactRelationship(
                relationship_id=uuid.uuid4(),
                project_id=pid,
                fact_a_id=fact_id_map[r["fact_a_ref"]],
                fact_b_id=fact_id_map[r["fact_b_ref"]],
                relationship_type=r["relationship_type"],
                reconciliation_basis=r.get("reconciliation_basis"),
                explanation=r.get("explanation", ""),
                confidence=r.get("confidence", 0.0),
                investigation_trail=r.get("investigation_trail", []),
            )
        )
    for c in proj.get("concepts", []):
        session.add(
            CanonicalConcept(
                concept_id=uuid.uuid4(),
                project_id=pid,
                kind=c["kind"],
                canonical_name=c["canonical_name"],
                raw_aliases=c.get("raw_aliases", []),
                first_seen_document_id=doc_id_map.get(c.get("first_seen_document_ref", "")),
            )
        )


# -------------------------------------------------------------------------- build
async def _build(full: bool) -> int:
    from app.comparison.pipeline import compare_document
    from app.domain import profile_new_document
    from app.extraction import extract_document
    from app.extraction.persist import persist_facts
    from app.ingestion import ingest_pdf
    from app.ingestion.persist import persist_ingestion
    from app.models.project import Project as ProjectModel
    from app.providers.factory import get_embedding_provider, get_llm_provider
    from app.verification import verify_extraction
    from app.verification.persist import persist_verification

    if not DATASETS.is_dir():
        print(f"datasets/ not found at {DATASETS}", file=sys.stderr)
        return 2

    llm = get_llm_provider()
    embedder = get_embedding_provider()
    engine = _engine()
    maker = async_sessionmaker(engine, expire_on_commit=False)
    out_projects: list[dict] = []

    for project_name, docs in _PLAN.items():
        print(f"\n=== {project_name} ===")
        async with maker() as session:
            project = ProjectModel(
                project_id=uuid.uuid4(), name=f"__seedbuild__{project_name}", domain_profile={}
            )
            session.add(project)
            await session.commit()
            pid = project.project_id

        for rel_path, pages in docs:
            path = DATASETS / rel_path
            if not path.is_file():
                print(f"  missing {rel_path}, skipping")
                continue
            print(f"  {rel_path} pages={pages if not full else 'all'}")
            data = path.read_bytes()
            ingestion = ingest_pdf(data, path.name, render_images=False)

            async with maker() as s:
                doc = await persist_ingestion(
                    s, pid, ingestion, byte_size=len(data), status="extracting"
                )
                did = doc.document_id
                await s.commit()

            extraction = await extract_document(
                ingestion,
                provider=llm,
                document_id=str(did),
                pages=None if full else pages,
            )
            async with maker() as s:
                rows = await persist_facts(s, pid, did, extraction)
                fact_ids = [r.fact_id for r in rows]
                await s.commit()

            verification = await verify_extraction(
                extraction, ingestion.chunks, provider=llm, concurrency=1
            )
            async with maker() as s:
                await persist_verification(s, pid, fact_ids, verification)
                await s.commit()

            async with maker() as s:
                chunk_texts = [c.text for c in ingestion.chunks]
                assignment = await profile_new_document(s, pid, did, chunk_texts, embedder=embedder)
                await s.commit()
            async with maker() as s:
                await compare_document(
                    s, pid, did, llm=llm, embedder=embedder, off_domain=assignment.off_domain
                )
                await s.commit()

        async with maker() as s:
            out_projects.append(await _export_project(s, pid, project_name))
        async with maker() as s:
            proj = await s.get(ProjectModel, pid)
            if proj is not None:
                await s.delete(proj)
                await s.commit()

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps({"projects": out_projects}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    await llm.aclose()
    await engine.dispose()
    n = sum(len(p["facts"]) for p in out_projects)
    print(f"\nwrote {SNAPSHOT_PATH} ({len(out_projects)} projects, {n} facts)")
    return 0


async def _export_project(session: Any, pid: uuid.UUID, name: str) -> dict:
    proj = await session.get(Project, pid)
    docs = (
        (await session.execute(select(Document).where(Document.project_id == pid))).scalars().all()
    )
    chunks = (await session.execute(select(Chunk).where(Chunk.project_id == pid))).scalars().all()
    facts = (await session.execute(select(Fact).where(Fact.project_id == pid))).scalars().all()
    rels = (
        (await session.execute(select(FactRelationship).where(FactRelationship.project_id == pid)))
        .scalars()
        .all()
    )
    concepts = (
        (await session.execute(select(CanonicalConcept).where(CanonicalConcept.project_id == pid)))
        .scalars()
        .all()
    )

    doc_ref = {d.document_id: f"doc-{i}" for i, d in enumerate(docs)}
    chunk_ref = {c.chunk_id: f"chunk-{i}" for i, c in enumerate(chunks)}
    fact_ref = {f.fact_id: f"fact-{i}" for i, f in enumerate(facts)}

    return {
        "name": name,
        "domain_profile": proj.domain_profile if proj else {},
        "documents": [
            {
                "ref": doc_ref[d.document_id],
                "filename": d.filename,
                "content_hash": d.content_hash,
                "byte_size": d.byte_size,
                "content_type_detected": d.content_type_detected,
                "page_count": d.page_count,
                "ocr_page_count": d.ocr_page_count,
                "routing_profile": d.routing_profile,
                "sub_cluster_id": d.sub_cluster_id,
                "off_domain": d.off_domain,
            }
            for d in docs
        ],
        "chunks": [
            {
                "ref": chunk_ref[c.chunk_id],
                "document_ref": doc_ref[c.document_id],
                "chunk_index": c.chunk_index,
                "page_number": c.page_number,
                "text": c.text,
                "leading_context": c.leading_context,
                "char_start": c.char_start,
                "char_end": c.char_end,
                "content_type": c.content_type,
                "has_table": c.has_table,
                "table_markdown": c.table_markdown,
                "confidence_ceiling": c.confidence_ceiling,
            }
            for c in chunks
            if c.chunk_id in {f.chunk_id for f in facts}
        ],
        "facts": [
            {
                "ref": fact_ref[f.fact_id],
                "document_ref": doc_ref[f.document_id],
                "chunk_ref": chunk_ref.get(f.chunk_id, ""),
                "source_anchor": f.source_anchor,
                "page_number": f.page_number,
                "fact_kind": f.fact_kind,
                "entity": f.entity,
                "entity_resolved": f.entity_resolved,
                "attribute": f.attribute,
                "value": f.value,
                "period": f.period,
                "qualifiers": f.qualifiers,
                "evidence_text": f.evidence_text,
                "verification_status": f.verification_status,
                "extraction_confidence": f.extraction_confidence,
                "verifier_confidence": f.verifier_confidence,
                "notes": f.notes,
            }
            for f in facts
        ],
        "relationships": [
            {
                "fact_a_ref": fact_ref[r.fact_a_id],
                "fact_b_ref": fact_ref[r.fact_b_id],
                "relationship_type": r.relationship_type,
                "reconciliation_basis": r.reconciliation_basis,
                "explanation": r.explanation,
                "confidence": r.confidence,
                "investigation_trail": r.investigation_trail,
            }
            for r in rels
            if r.fact_a_id in fact_ref and r.fact_b_id in fact_ref
        ],
        "concepts": [
            {
                "kind": c.kind,
                "canonical_name": c.canonical_name,
                "raw_aliases": c.raw_aliases,
                "first_seen_document_ref": doc_ref.get(c.first_seen_document_id, ""),
            }
            for c in concepts
        ],
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="scripts.seed")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("load")
    b = sub.add_parser("build")
    b.add_argument("--full", action="store_true", help="process every page (very slow)")
    args = parser.parse_args(argv)

    if args.command == "load":
        return asyncio.run(_load())
    return asyncio.run(_build(full=args.full))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

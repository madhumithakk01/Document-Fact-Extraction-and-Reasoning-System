"""Fact endpoints: filtered list, detail, and the evidence view."""

from __future__ import annotations

import uuid
from pathlib import Path

import pymupdf
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import project_scope
from app.api.pipeline_task import stored_pdf_path
from app.api.schemas import BBox, EvidenceOut, FactOut
from app.models.document import Chunk
from app.repository import get_document, get_fact, list_facts
from app.repository.scope import ProjectScope

router = APIRouter(prefix="/projects/{project_id}/facts", tags=["facts"])

_PAGE_IMAGE_MOUNT = "/media/page-images"


@router.get("", response_model=list[FactOut])
async def index(
    scope: ProjectScope = Depends(project_scope),
    entity: str | None = None,
    attribute: str | None = None,
    fact_kind: str | None = None,
    verification_status: str | None = None,
    document_id: uuid.UUID | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[FactOut]:
    facts = await list_facts(
        scope,
        entity=entity,
        attribute=attribute,
        fact_kind=fact_kind,
        verification_status=verification_status,
        document_id=document_id,
        limit=limit,
        offset=offset,
    )
    return [FactOut.of(f) for f in facts]


@router.get("/{fact_id}", response_model=FactOut)
async def show(fact_id: uuid.UUID, scope: ProjectScope = Depends(project_scope)) -> FactOut:
    fact = await get_fact(scope, fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail=f"fact {fact_id} not found")
    return FactOut.of(fact)


@router.get("/{fact_id}/evidence", response_model=EvidenceOut)
async def evidence(fact_id: uuid.UUID, scope: ProjectScope = Depends(project_scope)) -> EvidenceOut:
    fact = await get_fact(scope, fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail=f"fact {fact_id} not found")

    chunk: Chunk | None = None
    if fact.chunk_id is not None:
        chunk = await scope.session.get(Chunk, fact.chunk_id)
    document = await get_document(scope, fact.document_id)
    filename = document.filename if document else "document.pdf"

    page_image_url = None
    if chunk is not None and chunk.page_image_ref:
        page_image_url = f"{_PAGE_IMAGE_MOUNT}/{chunk.page_image_ref}"

    anchor = fact.source_anchor or {}
    span_text = anchor.get("matched_text") or fact.evidence_text

    page_width = page_height = None
    bboxes: list[BBox] = []
    normalized: list[BBox] = []

    pdf_path = stored_pdf_path(document.content_hash) if document else Path("/nonexistent")
    if fact.page_number and pdf_path.is_file():
        try:
            with pymupdf.open(pdf_path) as doc:
                page = doc[fact.page_number - 1]
                page_width, page_height = float(page.rect.width), float(page.rect.height)
                rects = page.search_for(span_text) or page.search_for(fact.evidence_text[:80])
                for r in rects:
                    bboxes.append(BBox(x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1))
                    normalized.append(
                        BBox(
                            x0=r.x0 / page_width,
                            y0=r.y0 / page_height,
                            x1=r.x1 / page_width,
                            y1=r.y1 / page_height,
                        )
                    )
        except Exception:  # noqa: BLE001 - evidence view degrades to text-only
            bboxes, normalized = [], []

    return EvidenceOut(
        fact_id=fact.fact_id,
        document_id=fact.document_id,
        filename=filename,
        page_number=fact.page_number,
        evidence_text=fact.evidence_text,
        surrounding_text=(chunk.text if chunk is not None else fact.evidence_text),
        page_image_url=page_image_url,
        page_width=page_width,
        page_height=page_height,
        highlight_bboxes=bboxes,
        highlight_bboxes_normalized=normalized,
    )

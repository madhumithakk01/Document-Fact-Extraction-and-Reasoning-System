"""Document endpoints: upload (async processing), list, detail, status, delete."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select

from app.api.deps import project_scope
from app.api.pipeline_task import process_document, stored_pdf_path
from app.api.schemas import DocumentOut, DocumentStatus
from app.models.document import Chunk, Document
from app.models.fact import Fact
from app.models.relationship import FactRelationship
from app.repository import get_document, list_documents
from app.repository.scope import ProjectScope

router = APIRouter(prefix="/projects/{project_id}/documents", tags=["documents"])

_MAX_BYTES = 60 * 1024 * 1024


@router.post("", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
async def upload(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    scope: ProjectScope = Depends(project_scope),
) -> DocumentOut:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds 60 MB limit")
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=415, detail="not a PDF")

    content_hash = hashlib.sha256(data).hexdigest()
    existing = (
        await scope.session.execute(
            select(Document).where(
                Document.project_id == scope.project_id,
                Document.content_hash == content_hash,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"document already in this project as {existing.document_id}",
        )

    stored_pdf_path(content_hash).write_bytes(data)
    document = Document(
        document_id=uuid.uuid4(),
        project_id=scope.project_id,
        filename=file.filename or "document.pdf",
        content_hash=content_hash,
        byte_size=len(data),
        content_type_detected="pending",
        processing_status="queued",
        routing_profile={},
        uploaded_at=datetime.now(UTC),
    )
    scope.session.add(document)
    # commit before scheduling so the background worker's own session sees the row
    await scope.session.commit()

    background.add_task(process_document, document.document_id, scope.project_id)
    return DocumentOut.of(document)


@router.get("", response_model=list[DocumentOut])
async def index(scope: ProjectScope = Depends(project_scope)) -> list[DocumentOut]:
    return [DocumentOut.of(d) for d in await list_documents(scope)]


async def _load(scope: ProjectScope, document_id: uuid.UUID) -> Document:
    doc = await get_document(scope, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"document {document_id} not found")
    return doc


@router.get("/{document_id}", response_model=DocumentOut)
async def show(document_id: uuid.UUID, scope: ProjectScope = Depends(project_scope)) -> DocumentOut:
    return DocumentOut.of(await _load(scope, document_id))


@router.get("/{document_id}/status", response_model=DocumentStatus)
async def poll_status(
    document_id: uuid.UUID, scope: ProjectScope = Depends(project_scope)
) -> DocumentStatus:
    doc = await _load(scope, document_id)
    s = scope.session

    chunk_count = int(
        await s.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.document_id == document_id)
        )
    )
    fact_count = int(
        await s.scalar(
            select(func.count()).select_from(Fact).where(Fact.document_id == document_id)
        )
    )
    by_status = {
        str(k): int(n)
        for k, n in (
            await s.execute(
                select(Fact.verification_status, func.count())
                .where(Fact.document_id == document_id)
                .group_by(Fact.verification_status)
            )
        ).all()
    }
    rel_count = int(
        await s.scalar(
            select(func.count())
            .select_from(FactRelationship)
            .where(
                FactRelationship.project_id == scope.project_id,
                FactRelationship.fact_a_id.in_(
                    select(Fact.fact_id).where(Fact.document_id == document_id)
                )
                | FactRelationship.fact_b_id.in_(
                    select(Fact.fact_id).where(Fact.document_id == document_id)
                ),
            )
        )
    )

    return DocumentStatus(
        document_id=doc.document_id,
        processing_status=doc.processing_status,
        processing_error=doc.processing_error,
        processing_detail=doc.processing_detail,
        pages_total=doc.pages_total,
        pages_processed=doc.pages_processed,
        page_count=doc.page_count,
        chunk_count=chunk_count,
        fact_count=fact_count,
        facts_by_status=by_status,
        relationship_count=rel_count,
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(document_id: uuid.UUID, scope: ProjectScope = Depends(project_scope)) -> None:
    await _load(scope, document_id)  # 404 if it is not in this project
    # chunks, facts, and (via facts) relationships are removed by ON DELETE CASCADE
    await scope.session.execute(
        sa_delete(Document).where(
            Document.project_id == scope.project_id, Document.document_id == document_id
        )
    )
    await scope.session.flush()


@router.post(
    "/{document_id}/retry",
    response_model=DocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry(
    background: BackgroundTasks,
    document_id: uuid.UUID,
    scope: ProjectScope = Depends(project_scope),
) -> DocumentOut:
    doc = await _load(scope, document_id)
    if doc.processing_status != "failed":
        raise HTTPException(
            status_code=409,
            detail=f"document is '{doc.processing_status}', only failed documents can be retried",
        )
    doc.processing_status = "queued"
    doc.processing_error = None
    doc.processing_detail = None
    doc.pages_processed = 0
    await scope.session.commit()

    background.add_task(process_document, doc.document_id, scope.project_id)
    return DocumentOut.of(doc)

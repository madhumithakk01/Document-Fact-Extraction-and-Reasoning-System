"""Write an ``IngestionResult`` to the database.

Idempotent on ``(project_id, content_hash)``: re-ingesting the same file into
the same project replaces its chunks rather than duplicating the document.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.types import IngestionResult
from app.models.document import Chunk, Document


async def persist_ingestion(
    session: AsyncSession,
    project_id: uuid.UUID,
    result: IngestionResult,
    *,
    byte_size: int,
    status: str = "extracting",
) -> Document:
    existing = (
        await session.execute(
            select(Document).where(
                Document.project_id == project_id,
                Document.content_hash == result.content_hash,
            )
        )
    ).scalar_one_or_none()

    profile = result.profile
    routing_profile = profile.model_dump()

    if existing is None:
        document = Document(
            document_id=uuid.uuid4(),
            project_id=project_id,
            filename=result.filename,
            content_hash=result.content_hash,
            byte_size=byte_size,
            content_type_detected=profile.content_type.value,
            processing_status=status,
            page_count=profile.page_count,
            ocr_page_count=profile.ocr_pages,
            routing_profile=routing_profile,
            uploaded_at=datetime.now(UTC),
        )
        session.add(document)
    else:
        document = existing
        document.filename = result.filename
        document.byte_size = byte_size
        document.content_type_detected = profile.content_type.value
        document.processing_status = status
        document.page_count = profile.page_count
        document.ocr_page_count = profile.ocr_pages
        document.routing_profile = routing_profile
        document.uploaded_at = document.uploaded_at or datetime.now(UTC)
        await session.execute(delete(Chunk).where(Chunk.document_id == document.document_id))

    await session.flush()

    for c in result.chunks:
        session.add(
            Chunk(
                chunk_id=uuid.uuid4(),
                document_id=document.document_id,
                project_id=project_id,
                chunk_index=c.index,
                page_number=c.page_number,
                text=c.text,
                leading_context=c.leading_context,
                char_start=c.char_start,
                char_end=c.char_end,
                content_type=c.content_type.value,
                has_table=c.has_table,
                table_markdown=c.table_markdown,
                page_image_ref=c.image_ref,
                confidence_ceiling=c.confidence_ceiling,
            )
        )
    await session.flush()
    return document

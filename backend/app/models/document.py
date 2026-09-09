"""Document and Chunk tables."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.constants import EMBEDDING_DIM


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("project_id", "content_hash", name="uq_documents_project_id_content_hash"),
        Index("ix_documents_project_id", "project_id"),
        Index("ix_documents_routing_profile", "routing_profile", postgresql_using="gin"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)

    content_type_detected: Mapped[str] = mapped_column(String(32), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # live progress while processing: a human-facing line ("extracting 23/95
    # pages", "rate limited, retrying 3/5") plus page counters the UI polls
    processing_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    pages_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pages_processed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # extraction survivorship: how many candidate facts the model proposed vs how
    # many were kept, so the evaluation view can report an honest yield rate
    # rather than a rate over only the facts that survived to storage.
    extraction_stats: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ocr_page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    routing_profile: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    doc_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    # domain profiling: which sub-cluster this document was placed in, and whether
    # it looked topically different from everything already in the project
    sub_cluster_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    off_domain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="Chunk.chunk_index",
    )


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_id_chunk_index"),
        Index("ix_chunks_project_id", "project_id"),
        Index("ix_chunks_document_id", "document_id"),
    )

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    leading_context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    char_start: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    has_table: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    table_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_image_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    confidence_ceiling: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    document: Mapped[Document] = relationship(back_populates="chunks")

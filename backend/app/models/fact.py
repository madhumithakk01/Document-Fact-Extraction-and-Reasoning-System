"""Fact table.

Raw candidate facts land here unverified (``verification_status = 'pending'``).
The verification loop updates the status and fills ``verifier_confidence``;
normalization adds the embedding column and its index in a later phase. Every
row carries ``project_id`` for the hard project partition.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Fact(Base, TimestampMixin):
    __tablename__ = "facts"
    __table_args__ = (
        Index("ix_facts_project_id", "project_id"),
        Index("ix_facts_document_id", "document_id"),
        Index("ix_facts_chunk_id", "chunk_id"),
        Index("ix_facts_verification_status", "verification_status"),
    )

    fact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chunks.chunk_id", ondelete="SET NULL"), nullable=True
    )

    # location of the evidence span
    source_anchor: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    page_number: Mapped[int | None] = mapped_column(nullable=True)

    fact_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    entity: Mapped[str] = mapped_column(Text, nullable=False)
    entity_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    attribute: Mapped[str] = mapped_column(Text, nullable=False)

    value: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    period: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    qualifiers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)

    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    verifier_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    notes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

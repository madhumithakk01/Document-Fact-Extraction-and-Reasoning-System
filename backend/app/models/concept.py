"""CanonicalConcept table.

A confirmed merge of entity or attribute strings that name the same thing within
a project, with the raw aliases seen and the document that first introduced it.
Feeds the ontology growth view.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.constants import CONCEPT_KINDS

_KIND_CHECK = ", ".join(f"'{k}'" for k in CONCEPT_KINDS)


class CanonicalConcept(Base, TimestampMixin):
    __tablename__ = "canonical_concepts"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "kind",
            "canonical_name",
            name="uq_canonical_concepts_project_id_kind_canonical_name",
        ),
        CheckConstraint(f"kind in ({_KIND_CHECK})", name="concept_kind_allowed"),
        Index("ix_canonical_concepts_project_id", "project_id"),
        Index("ix_canonical_concepts_aliases", "raw_aliases", postgresql_using="gin"),
    )

    concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )

    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(300), nullable=False)
    raw_aliases: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    first_seen_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.document_id", ondelete="SET NULL"), nullable=True
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

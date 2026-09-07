"""FactRelationship table.

The pairwise verdict between two facts in the same project: corroborates,
contradicts, reconciled_by_context (with a named basis), or unrelated. When the
reconciliation agent ran, ``investigation_trail`` holds its tool calls and
results. Both facts always belong to the same project as the relationship.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.constants import RELATIONSHIP_TYPES

_TYPE_CHECK = ", ".join(f"'{t}'" for t in RELATIONSHIP_TYPES)


class FactRelationship(Base, TimestampMixin):
    __tablename__ = "fact_relationships"
    __table_args__ = (
        UniqueConstraint(
            "fact_a_id", "fact_b_id", name="uq_fact_relationships_fact_a_id_fact_b_id"
        ),
        CheckConstraint(
            f"relationship_type in ({_TYPE_CHECK})",
            name="relationship_type_allowed",
        ),
        CheckConstraint("fact_a_id <> fact_b_id", name="distinct_facts"),
        Index("ix_fact_relationships_project_id", "project_id"),
        Index("ix_fact_relationships_fact_a_id", "fact_a_id"),
        Index("ix_fact_relationships_fact_b_id", "fact_b_id"),
        Index("ix_fact_relationships_type", "project_id", "relationship_type"),
        Index("ix_fact_relationships_trail", "investigation_trail", postgresql_using="gin"),
    )

    relationship_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False
    )
    fact_a_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facts.fact_id", ondelete="CASCADE"), nullable=False
    )
    fact_b_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facts.fact_id", ondelete="CASCADE"), nullable=False
    )

    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reconciliation_basis: Mapped[str | None] = mapped_column(String(200), nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    investigation_trail: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

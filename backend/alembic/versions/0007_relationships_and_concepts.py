"""fact_relationships and canonical_concepts

Revision ID: 0007_relationships_and_concepts
Revises: 0006_vector_columns
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.models.constants import CONCEPT_KINDS, RELATIONSHIP_TYPES

revision: str = "0007_relationships_and_concepts"
down_revision: str | None = "0006_vector_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REL_TYPES = ", ".join(f"'{t}'" for t in RELATIONSHIP_TYPES)
_KINDS = ", ".join(f"'{k}'" for k in CONCEPT_KINDS)


def upgrade() -> None:
    op.create_table(
        "fact_relationships",
        sa.Column("relationship_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fact_a_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fact_b_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_type", sa.String(length=32), nullable=False),
        sa.Column("reconciliation_basis", sa.String(length=64), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("investigation_trail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("relationship_id", name="pk_fact_relationships"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_fact_relationships_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fact_a_id"],
            ["facts.fact_id"],
            name="fk_fact_relationships_fact_a_id_facts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fact_b_id"],
            ["facts.fact_id"],
            name="fk_fact_relationships_fact_b_id_facts",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "fact_a_id", "fact_b_id", name="uq_fact_relationships_fact_a_id_fact_b_id"
        ),
        sa.CheckConstraint(
            f"relationship_type in ({_REL_TYPES})",
            name="ck_fact_relationships_relationship_type_allowed",
        ),
        sa.CheckConstraint("fact_a_id <> fact_b_id", name="ck_fact_relationships_distinct_facts"),
    )
    op.create_index("ix_fact_relationships_project_id", "fact_relationships", ["project_id"])
    op.create_index("ix_fact_relationships_fact_a_id", "fact_relationships", ["fact_a_id"])
    op.create_index("ix_fact_relationships_fact_b_id", "fact_relationships", ["fact_b_id"])
    op.create_index(
        "ix_fact_relationships_type", "fact_relationships", ["project_id", "relationship_type"]
    )
    op.create_index(
        "ix_fact_relationships_trail",
        "fact_relationships",
        ["investigation_trail"],
        postgresql_using="gin",
    )

    op.create_table(
        "canonical_concepts",
        sa.Column("concept_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("canonical_name", sa.String(length=300), nullable=False),
        sa.Column("raw_aliases", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("first_seen_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("concept_id", name="pk_canonical_concepts"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_canonical_concepts_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["first_seen_document_id"],
            ["documents.document_id"],
            name="fk_canonical_concepts_first_seen_document_id_documents",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "project_id",
            "kind",
            "canonical_name",
            name="uq_canonical_concepts_project_id_kind_canonical_name",
        ),
        sa.CheckConstraint(
            f"kind in ({_KINDS})", name="ck_canonical_concepts_concept_kind_allowed"
        ),
    )
    op.create_index("ix_canonical_concepts_project_id", "canonical_concepts", ["project_id"])
    op.create_index(
        "ix_canonical_concepts_aliases",
        "canonical_concepts",
        ["raw_aliases"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_table("canonical_concepts")
    op.drop_table("fact_relationships")

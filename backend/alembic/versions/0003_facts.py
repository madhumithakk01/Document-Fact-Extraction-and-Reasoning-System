"""facts

Revision ID: 0003_facts
Revises: 0002_documents_and_chunks
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_facts"
down_revision: str | None = "0002_documents_and_chunks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "facts",
        sa.Column("fact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_anchor", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("fact_kind", sa.String(length=16), nullable=False),
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column("entity_resolved", sa.Boolean(), nullable=False),
        sa.Column("attribute", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("period", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("qualifiers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("verification_status", sa.String(length=20), nullable=False),
        sa.Column("extraction_confidence", sa.Float(), nullable=False),
        sa.Column("verifier_confidence", sa.Float(), nullable=True),
        sa.Column("notes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("fact_id", name="pk_facts"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.document_id"],
            name="fk_facts_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.chunk_id"],
            name="fk_facts_chunk_id_chunks",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_facts_project_id", "facts", ["project_id"])
    op.create_index("ix_facts_document_id", "facts", ["document_id"])
    op.create_index("ix_facts_chunk_id", "facts", ["chunk_id"])
    op.create_index("ix_facts_verification_status", "facts", ["verification_status"])


def downgrade() -> None:
    op.drop_table("facts")

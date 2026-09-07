"""documents and chunks

Revision ID: 0002_documents_and_chunks
Revises: 0001_enable_pgvector
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_documents_and_chunks"
down_revision: str | None = "0001_enable_pgvector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("content_type_detected", sa.String(length=32), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("ocr_page_count", sa.Integer(), nullable=False),
        sa.Column("routing_profile", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("document_id", name="pk_documents"),
        sa.UniqueConstraint(
            "project_id", "content_hash", name="uq_documents_project_id_content_hash"
        ),
    )
    op.create_index("ix_documents_project_id", "documents", ["project_id"])

    op.create_table(
        "chunks",
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("leading_context", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("has_table", sa.Boolean(), nullable=False),
        sa.Column("table_markdown", sa.Text(), nullable=True),
        sa.Column("page_image_ref", sa.String(length=1024), nullable=True),
        sa.Column("confidence_ceiling", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("chunk_id", name="pk_chunks"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.document_id"],
            name="fk_chunks_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_id_chunk_index"),
    )
    op.create_index("ix_chunks_project_id", "chunks", ["project_id"])
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])


def downgrade() -> None:
    op.drop_table("chunks")
    op.drop_index("ix_documents_project_id", table_name="documents")
    op.drop_table("documents")

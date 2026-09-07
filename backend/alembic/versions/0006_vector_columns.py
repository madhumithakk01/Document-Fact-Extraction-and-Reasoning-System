"""embedding columns and HNSW indexes

Revision ID: 0006_vector_columns
Revises: 0005_projects
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op
from app.models.constants import EMBEDDING_DIM

revision: str = "0006_vector_columns"
down_revision: str | None = "0005_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HNSW_OPTS = {
    "postgresql_using": "hnsw",
    "postgresql_with": {"m": 16, "ef_construction": 64},
}


def upgrade() -> None:
    op.add_column("documents", sa.Column("doc_embedding", Vector(EMBEDDING_DIM), nullable=True))
    op.add_column("facts", sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True))

    op.create_index(
        "ix_documents_doc_embedding_hnsw",
        "documents",
        ["doc_embedding"],
        postgresql_ops={"doc_embedding": "vector_cosine_ops"},
        **_HNSW_OPTS,
    )
    op.create_index(
        "ix_facts_embedding_hnsw",
        "facts",
        ["embedding"],
        postgresql_ops={"embedding": "vector_cosine_ops"},
        **_HNSW_OPTS,
    )


def downgrade() -> None:
    op.drop_index("ix_facts_embedding_hnsw", table_name="facts")
    op.drop_index("ix_documents_doc_embedding_hnsw", table_name="documents")
    op.drop_column("facts", "embedding")
    op.drop_column("documents", "doc_embedding")

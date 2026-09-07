"""enable pgvector extension

Revision ID: 0001_enable_pgvector
Revises:
Create Date: 2026-09-07

The relational schema is defined in a later phase. This first migration only
provisions the vector extension so the database is ready for embedding columns.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_enable_pgvector"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")

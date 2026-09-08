"""document progress counters and human-facing detail

Revision ID: 0013_document_progress
Revises: 0012_widen_reconciliation_basis
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_document_progress"
down_revision: str | None = "0012_widen_reconciliation_basis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("pages_total", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("pages_processed", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("processing_detail", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "processing_detail")
    op.drop_column("documents", "pages_processed")
    op.drop_column("documents", "pages_total")

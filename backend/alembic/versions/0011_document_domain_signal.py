"""document sub_cluster_id and off_domain columns

Revision ID: 0011_document_domain_signal
Revises: 0010_document_processing_error
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_document_domain_signal"
down_revision: str | None = "0010_document_processing_error"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("sub_cluster_id", sa.String(length=32), nullable=True))
    op.add_column(
        "documents",
        sa.Column("off_domain", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("documents", "off_domain")
    op.drop_column("documents", "sub_cluster_id")

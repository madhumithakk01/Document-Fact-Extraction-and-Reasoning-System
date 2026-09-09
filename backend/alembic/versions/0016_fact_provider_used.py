"""tag each fact with the provider that produced it

Revision ID: 0016_fact_provider_used
Revises: 0015_document_extraction_stats
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_fact_provider_used"
down_revision: str | None = "0015_document_extraction_stats"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("facts", sa.Column("provider_used", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("facts", "provider_used")

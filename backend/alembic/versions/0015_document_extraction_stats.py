"""per-document extraction stats for honest grounding metrics

Revision ID: 0015_document_extraction_stats
Revises: 0014_fact_corrections
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015_document_extraction_stats"
down_revision: str | None = "0014_fact_corrections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "extraction_stats",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "extraction_stats")

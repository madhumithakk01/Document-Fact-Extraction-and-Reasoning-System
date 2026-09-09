"""independent dual-extraction corroboration result per fact

Revision ID: 0017_fact_corroboration
Revises: 0016_fact_provider_used
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017_fact_corroboration"
down_revision: str | None = "0016_fact_provider_used"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "facts",
        sa.Column("corroboration", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("facts", "corroboration")

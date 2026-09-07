"""make pre-existing timestamp columns timezone-aware

Revision ID: 0009_timestamptz
Revises: 0008_jsonb_and_scoped_indexes
Create Date: 2026-09-07

The document, fact, and verification-log tables were created with naive
``timestamp`` columns. The application works entirely in UTC and writes
timezone-aware datetimes, so these are converted to ``timestamptz`` (existing
values are read as UTC).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_timestamptz"
down_revision: str | None = "0008_jsonb_and_scoped_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = [
    ("documents", "created_at"),
    ("documents", "uploaded_at"),
    ("facts", "created_at"),
    ("verification_logs", "created_at"),
]


def upgrade() -> None:
    for table, column in _COLUMNS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE timestamptz "
            f"USING {column} AT TIME ZONE 'UTC'"
        )


def downgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(table, column, type_=sa.DateTime(timezone=False))

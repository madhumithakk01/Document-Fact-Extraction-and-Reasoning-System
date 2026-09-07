"""verification logs

Revision ID: 0004_verification_logs
Revises: 0003_facts
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_verification_logs"
down_revision: str | None = "0003_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "verification_logs",
        sa.Column("log_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.String(length=24), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("issue", sa.Text(), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("log_id", name="pk_verification_logs"),
        sa.ForeignKeyConstraint(
            ["fact_id"],
            ["facts.fact_id"],
            name="fk_verification_logs_fact_id_facts",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_verification_logs_project_id", "verification_logs", ["project_id"])
    op.create_index("ix_verification_logs_fact_id", "verification_logs", ["fact_id"])
    op.create_index("ix_verification_logs_stage", "verification_logs", ["stage"])


def downgrade() -> None:
    op.drop_table("verification_logs")

"""projects table and project foreign keys

Revision ID: 0005_projects
Revises: 0004_verification_logs
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_projects"
down_revision: str | None = "0004_verification_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCOPED_TABLES = ("documents", "chunks", "facts", "verification_logs")


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("domain_profile", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("project_id", name="pk_projects"),
    )
    for table in _SCOPED_TABLES:
        op.create_foreign_key(
            f"fk_{table}_project_id_projects",
            table,
            "projects",
            ["project_id"],
            ["project_id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    for table in _SCOPED_TABLES:
        op.drop_constraint(f"fk_{table}_project_id_projects", table, type_="foreignkey")
    op.drop_table("projects")

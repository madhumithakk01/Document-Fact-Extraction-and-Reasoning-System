"""widen fact_relationships.reconciliation_basis

Revision ID: 0012_widen_reconciliation_basis
Revises: 0011_document_domain_signal
Create Date: 2026-09-08

Adjudication sometimes names a basis longer than 64 characters ("gross fiscal
deficit vs overall balance; revised estimate vs projection").
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_widen_reconciliation_basis"
down_revision: str | None = "0011_document_domain_signal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "fact_relationships",
        "reconciliation_basis",
        type_=sa.String(length=200),
        existing_type=sa.String(length=64),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "fact_relationships",
        "reconciliation_basis",
        type_=sa.String(length=64),
        existing_type=sa.String(length=200),
        existing_nullable=True,
    )

"""GIN indexes on JSONB columns and project-scoped lookup indexes

Revision ID: 0008_jsonb_and_scoped_indexes
Revises: 0007_relationships_and_concepts
Create Date: 2026-09-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_jsonb_and_scoped_indexes"
down_revision: str | None = "0007_relationships_and_concepts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GIN = [
    ("ix_facts_qualifiers", "facts", "qualifiers"),
    ("ix_facts_value", "facts", "value"),
    ("ix_facts_period", "facts", "period"),
    ("ix_documents_routing_profile", "documents", "routing_profile"),
]


def upgrade() -> None:
    for name, table, column in _GIN:
        op.create_index(name, table, [column], postgresql_using="gin")
    # entity lookups are always within a project
    op.create_index("ix_facts_entity", "facts", ["project_id", "entity"])


def downgrade() -> None:
    op.drop_index("ix_facts_entity", table_name="facts")
    for name, table, _column in reversed(_GIN):
        op.drop_index(name, table_name=table)

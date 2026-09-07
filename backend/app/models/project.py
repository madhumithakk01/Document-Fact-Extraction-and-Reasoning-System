"""Project table -- the isolation boundary.

Every other row in the system belongs to exactly one project through a
``project_id`` foreign key. No query, index, or code path crosses that boundary.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

EMPTY_DOMAIN_PROFILE: dict[str, Any] = {
    "centroid_embedding": None,
    "sub_clusters": [],
    "vocabulary": [],
    "document_count": 0,
}


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    # rolling centroid, sub-clusters, and accumulated canonical vocabulary
    domain_profile: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=lambda: dict(EMPTY_DOMAIN_PROFILE)
    )

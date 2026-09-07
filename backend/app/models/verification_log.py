"""VerificationLog table.

One row per verification stage per fact, written whatever the outcome. This is
the raw material for the live evaluation metrics in a later phase.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class VerificationLog(Base, TimestampMixin):
    __tablename__ = "verification_logs"
    __table_args__ = (
        Index("ix_verification_logs_project_id", "project_id"),
        Index("ix_verification_logs_fact_id", "fact_id"),
        Index("ix_verification_logs_stage", "stage"),
    )

    log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facts.fact_id", ondelete="CASCADE"), nullable=False
    )

    stage: Mapped[str] = mapped_column(String(24), nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    issue: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

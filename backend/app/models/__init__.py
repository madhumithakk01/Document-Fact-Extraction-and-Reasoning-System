"""SQLAlchemy models. The full schema is finalized in a later phase; this
module currently exposes only the declarative base and metadata."""

from app.models.base import Base

__all__ = ["Base"]

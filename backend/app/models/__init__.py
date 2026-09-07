"""SQLAlchemy models. The full fact/relationship schema is finalized in a later
phase; ingestion introduces the document and chunk tables."""

from app.models.base import Base
from app.models.document import Chunk, Document
from app.models.fact import Fact

__all__ = ["Base", "Chunk", "Document", "Fact"]

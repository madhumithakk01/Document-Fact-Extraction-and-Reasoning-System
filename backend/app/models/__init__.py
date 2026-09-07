"""SQLAlchemy models. The full schema is finalized here: every entity is scoped
to a ``Project`` by a foreign key, and no relationship spans projects."""

from app.models.base import Base
from app.models.concept import CanonicalConcept
from app.models.constants import EMBEDDING_DIM
from app.models.document import Chunk, Document
from app.models.fact import Fact
from app.models.project import Project
from app.models.relationship import FactRelationship
from app.models.verification_log import VerificationLog

__all__ = [
    "EMBEDDING_DIM",
    "Base",
    "CanonicalConcept",
    "Chunk",
    "Document",
    "Fact",
    "FactRelationship",
    "Project",
    "VerificationLog",
]

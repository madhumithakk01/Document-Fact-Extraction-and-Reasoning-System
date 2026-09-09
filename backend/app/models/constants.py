"""Schema-level constants.

``EMBEDDING_DIM`` is fixed in the database (vector column width and its HNSW
index). It matches the default local embedding model, ``BAAI/bge-small-en-v1.5``.
Switching to a model with a different output width requires a migration that
rewrites the vector columns and indexes, so it is not a plain config change.
"""

EMBEDDING_DIM = 384

RELATIONSHIP_TYPES = (
    "corroborates",
    "contradicts",
    "reconciled_by_context",
    "unrelated",
)

CONCEPT_KINDS = ("entity", "attribute")

PROCESSING_STATUSES = (
    "queued",
    "extracting",
    "partially_ready",
    "verifying",
    "comparing",
    "ready",
    "failed",
    "extraction_unavailable",
)

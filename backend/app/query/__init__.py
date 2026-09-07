"""Reasoning console (BUILD_PHASES §8).

An open question runs through a bounded tool loop -- semantic and lexical fact
search, plus relationship lookups -- with a capped iteration count and a full
trace kept. The gathered facts are then synthesised into an answer where every
claim carries an inline citation to a specific fact, and any relevant
``contradicts`` (or ``reconciled_by_context``) relationship among those facts is
surfaced explicitly rather than resolved silently one way.
"""

from app.query.pipeline import run_query
from app.query.schema import (
    Citation,
    Disagreement,
    QueryResult,
    QueryTraceEntry,
)

__all__ = [
    "Citation",
    "Disagreement",
    "QueryResult",
    "QueryTraceEntry",
    "run_query",
]

"""Fact extraction.

One schema-constrained model call per chunk turns page text (and, for table
pages, the reconstructed grid) into candidate facts: an entity, an
open-vocabulary attribute, a typed value with an explicit comparator, a period,
free-form qualifiers, and a verbatim evidence span. Candidates are anchored back
to a character range in the source document and stored unverified; the
verification loop (next phase) decides which become usable.
"""

from app.extraction.extractor import extract_document, extract_from_chunk
from app.extraction.schema import (
    AnchoredFact,
    CandidateFact,
    Comparator,
    ExtractedPeriod,
    ExtractedValue,
    ExtractionResult,
    FactKind,
    SourceAnchor,
)

__all__ = [
    "AnchoredFact",
    "CandidateFact",
    "Comparator",
    "ExtractedPeriod",
    "ExtractedValue",
    "ExtractionResult",
    "FactKind",
    "SourceAnchor",
    "extract_document",
    "extract_from_chunk",
]

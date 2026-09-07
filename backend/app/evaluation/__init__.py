"""Live evaluation metrics (BUILD_PHASES §9).

Everything here is derived from ``VerificationLog`` rows and current ``Fact``
statuses at request time -- grounding pass rate, the independent-verification
outcome breakdown, the same per document, and a trend across documents as the
project grew. Nothing is stored or hardcoded.
"""

from app.evaluation.metrics import compute_evaluation
from app.evaluation.schema import (
    DocumentEvaluation,
    EvaluationReport,
    TimelinePoint,
)

__all__ = [
    "DocumentEvaluation",
    "EvaluationReport",
    "TimelinePoint",
    "compute_evaluation",
]

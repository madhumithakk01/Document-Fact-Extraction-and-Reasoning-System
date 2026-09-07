"""Verification loop.

Every extracted fact is checked before it can be treated as usable. First a
deterministic grounding check: is the evidence span really a substring of the
source chunk? Then an independent model call, given only the claim and its cited
span with no other document context, decides whether the text actually supports
that exact entity / attribute / value / unit / period. A single bounded
auto-correct-and-recheck is allowed for a clearly identified mistake; anything
still unresolved is kept and flagged ``needs_review``, never dropped. Every
outcome writes a ``VerificationLog`` row.
"""

from app.verification.pipeline import verify_extraction
from app.verification.schema import (
    FactVerification,
    GroundingResult,
    IndependentVerdict,
    IndependentVerification,
    VerificationLogEntry,
    VerificationOutcome,
    VerificationResult,
    VerificationStats,
)
from app.verification.verifier import verify_fact

__all__ = [
    "FactVerification",
    "GroundingResult",
    "IndependentVerdict",
    "IndependentVerification",
    "VerificationLogEntry",
    "VerificationOutcome",
    "VerificationResult",
    "VerificationStats",
    "verify_extraction",
    "verify_fact",
]

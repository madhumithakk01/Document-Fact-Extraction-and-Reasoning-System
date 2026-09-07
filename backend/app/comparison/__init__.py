"""Deterministic comparison.

Before any model call, :func:`deterministic_precheck` decides whether two facts
in a project can be resolved on the spot. It resolves only the one outcome it
can be certain of -- ``corroborates`` -- when the subjects match, the periods
are the same span, no significant qualifier differs, and the value intervals
overlap. Everything else (a real disagreement, a qualifier difference, a period
that only partly lines up) is handed to adjudication with a reason, never
guessed at here.

:func:`adjudicate_same_concept` is the small canonicalization decision for
whether two entity or attribute strings name the same thing; it too has
deterministic fast paths and only calls a model in the uncertain middle.
"""

from app.comparison.canonicalize import ConceptDecision, adjudicate_same_concept
from app.comparison.precheck import (
    ComparableFact,
    PrecheckOutcome,
    PrecheckResult,
    deterministic_precheck,
)

__all__ = [
    "ComparableFact",
    "ConceptDecision",
    "PrecheckOutcome",
    "PrecheckResult",
    "adjudicate_same_concept",
    "deterministic_precheck",
]

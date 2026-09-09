"""Silent-assumption detection and its cost to confidence.

The pipeline fills gaps a source leaves open: it reads an undated "FY24" with the
Indian April-March convention, keeps a value whose entity was inferred from
carried page context, keeps a number the extractor never attached a comparator
to. Each of those is a guess that could be wrong. This module names them so they
can be shown next to a fact and subtracted from its confidence, rather than
sitting silently in the data.
"""

from __future__ import annotations

from app.normalization.dates import PeriodKind, parse_period

# Each unresolved assumption costs this much confidence, down to the floor.
ASSUMPTION_PENALTY = 0.10
CONFIDENCE_FLOOR = 0.05

# Human-readable label per flag, for the API response and the frontend badge.
ASSUMPTION_LABELS: dict[str, str] = {
    "fy_convention_assumed": "FY convention assumed",
    "entity_inferred": "entity inferred from context",
    "comparator_unspecified": "comparator not stated",
}

# Period kinds whose start/end depend on the fiscal-year boundary month.
_FY_DEPENDENT = frozenset(
    {
        PeriodKind.fiscal_year,
        PeriodKind.quarter,
        PeriodKind.half,
        PeriodKind.multi_year,
    }
)


def detect_assumptions(
    *,
    fact_kind: str,
    entity_resolved: bool,
    value: dict | None,
    period_label: str | None,
) -> list[str]:
    """Return the assumption flags that apply to one fact, in a stable order."""
    flags: list[str] = []

    if not entity_resolved:
        flags.append("entity_inferred")

    if fact_kind == "quantitative" and not (value or {}).get("comparator"):
        flags.append("comparator_unspecified")

    if period_label:
        period = parse_period(period_label)
        if period.convention_assumed and period.kind in _FY_DEPENDENT:
            flags.append("fy_convention_assumed")

    return flags


def penalize_confidence(confidence: float, flags: list[str]) -> float:
    """Subtract the per-flag penalty, never dropping below the floor."""
    if not flags:
        return confidence
    return max(CONFIDENCE_FLOOR, confidence - ASSUMPTION_PENALTY * len(flags))

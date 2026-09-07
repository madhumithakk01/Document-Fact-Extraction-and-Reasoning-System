"""Significant-qualifier comparison.

Some qualifiers change what a value *means* -- the basis it is measured on, its
currency, whether it is audited, standalone vs consolidated, actual vs forecast,
and who is asserting it. If two facts disagree on one of these, the deterministic
pre-check must not resolve them; the difference goes to adjudication so the
reasoning about it is captured.
"""

from __future__ import annotations

# canonical significant-qualifier name -> the raw keys that map onto it
_SIGNIFICANT: dict[str, tuple[str, ...]] = {
    "basis": ("basis", "measurement_basis", "accounting_basis"),
    "currency": ("currency", "reporting_currency"),
    "audited": ("audited", "audit_status", "auditing_status"),
    "consolidation": (
        "consolidation",
        "consolidated",
        "consolidated_vs_standalone",
        "standalone_vs_consolidated",
        "consolidation_basis",
    ),
    "forecast_vs_actual": (
        "forecast_vs_actual",
        "actual_vs_forecast",
        "actual_or_forecast",
        "estimate_vs_actual",
        "projection_vs_actual",
    ),
    "asserting_party": ("asserting_party", "source", "reported_by", "publisher"),
    "scope": ("scope", "segment", "geography", "region"),
}

_VALUE_SYNONYMS: dict[str, str] = {
    "consolidated": "consolidated",
    "consol": "consolidated",
    "standalone": "standalone",
    "unconsolidated": "standalone",
    "audited": "audited",
    "unaudited": "unaudited",
    "reviewed": "unaudited",
    "actual": "actual",
    "actuals": "actual",
    "forecast": "forecast",
    "forecasted": "forecast",
    "projected": "forecast",
    "projection": "forecast",
    "estimate": "forecast",
    "estimated": "forecast",
    "guidance": "forecast",
    "yes": "true",
    "no": "false",
    "true": "true",
    "false": "false",
}


def _canon_value(raw: object) -> str:
    s = str(raw).strip().lower()
    return _VALUE_SYNONYMS.get(s, s)


def significant_qualifiers(qualifiers: dict) -> dict[str, str]:
    """Map a fact's raw qualifiers onto canonical significant ones."""
    lowered = {str(k).strip().lower(): v for k, v in (qualifiers or {}).items()}
    out: dict[str, str] = {}
    for canon, keys in _SIGNIFICANT.items():
        for key in keys:
            if key in lowered and str(lowered[key]).strip():
                out[canon] = _canon_value(lowered[key])
                break
    return out


def differing_significant_qualifiers(a: dict, b: dict) -> list[str]:
    """Canonical qualifier names where both facts state a value and the values
    disagree. A qualifier only one side states is not a disagreement here."""
    sa = significant_qualifiers(a)
    sb = significant_qualifiers(b)
    return sorted(k for k in sa.keys() & sb.keys() if sa[k] != sb[k])

"""The deterministic comparison pre-check (§6.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.comparison.qualifiers import differing_significant_qualifiers
from app.normalization.dates import parse_period, periods_relation
from app.normalization.units import Dimension
from app.normalization.value import normalize_value


class PrecheckOutcome(StrEnum):
    corroborates = "corroborates"
    needs_adjudication = "needs_adjudication"
    not_comparable = "not_comparable"


# dimensions that measure a concrete physical/financial quantity: pairing one of
# these with an unclassified unit is a genuine mismatch, not just a gap
_CONCRETE_DIMENSIONS = frozenset(
    {
        Dimension.currency,
        Dimension.percent,
        Dimension.mass,
        Dimension.length,
        Dimension.area,
        Dimension.duration,
        Dimension.ratio,
    }
)


@dataclass(frozen=True, slots=True)
class ComparableFact:
    fact_kind: str
    entity: str
    attribute: str
    value: dict
    period: dict
    qualifiers: dict = field(default_factory=dict)
    canonical_entity: str | None = None
    canonical_attribute: str | None = None
    # False when extraction had to infer the entity from carried page context
    # rather than read it on the page itself
    entity_resolved: bool = True

    @classmethod
    def from_fact(cls, fact: Any) -> ComparableFact:
        return cls(
            fact_kind=fact.fact_kind,
            entity=fact.entity,
            attribute=fact.attribute,
            value=dict(fact.value or {}),
            period=dict(fact.period or {}),
            qualifiers=dict(fact.qualifiers or {}),
            entity_resolved=getattr(fact, "entity_resolved", True),
        )

    def _entity_key(self) -> str:
        return _norm(self.canonical_entity or self.entity)

    def _attribute_key(self) -> str:
        return _norm(self.canonical_attribute or self.attribute)


@dataclass(frozen=True, slots=True)
class PrecheckResult:
    outcome: PrecheckOutcome
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def resolved(self) -> bool:
        return self.outcome is PrecheckOutcome.corroborates


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def deterministic_precheck(a: ComparableFact, b: ComparableFact) -> PrecheckResult:
    if a.fact_kind != b.fact_kind:
        return PrecheckResult(
            PrecheckOutcome.not_comparable,
            f"different fact kinds ({a.fact_kind} vs {b.fact_kind})",
        )

    if a._entity_key() != b._entity_key():
        return PrecheckResult(
            PrecheckOutcome.not_comparable,
            "entities are not the same canonical concept",
            {"entity_a": a._entity_key(), "entity_b": b._entity_key()},
        )
    if a._attribute_key() != b._attribute_key():
        return PrecheckResult(
            PrecheckOutcome.not_comparable,
            "attributes are not the same canonical concept",
            {"attribute_a": a._attribute_key(), "attribute_b": b._attribute_key()},
        )

    # --- period compatibility ---
    pa = parse_period(a.period.get("raw_label"))
    pb = parse_period(b.period.get("raw_label"))
    relation = periods_relation(pa, pb)
    if relation == "disjoint":
        return PrecheckResult(
            PrecheckOutcome.not_comparable,
            "periods are different, non-overlapping spans",
            {"period_a": pa.raw_label, "period_b": pb.raw_label},
        )
    if relation in ("a_contains_b", "b_contains_a", "overlap"):
        return PrecheckResult(
            PrecheckOutcome.needs_adjudication,
            "periods overlap but are not the same span",
            {"relation": relation, "period_a": pa.raw_label, "period_b": pb.raw_label},
        )
    if relation == "unknown" and _norm(a.period.get("raw_label", "")) != _norm(
        b.period.get("raw_label", "")
    ):
        return PrecheckResult(
            PrecheckOutcome.needs_adjudication,
            "period labels differ and could not be resolved to dates",
            {"period_a": a.period.get("raw_label"), "period_b": b.period.get("raw_label")},
        )

    def _corroborates(reason: str, detail: dict[str, Any] | None = None) -> PrecheckResult:
        # A deterministic "corroborates" is recorded with no model call, so it must
        # not rest on an entity that extraction only inferred from page context.
        if not (a.entity_resolved and b.entity_resolved):
            return PrecheckResult(
                PrecheckOutcome.needs_adjudication,
                "an entity was inferred from carried page context, not stated on the page; "
                "confirm both facts are about the same subject",
                {
                    **(detail or {}),
                    "entity_resolved_a": a.entity_resolved,
                    "entity_resolved_b": b.entity_resolved,
                },
            )
        return PrecheckResult(PrecheckOutcome.corroborates, reason, detail or {})

    # --- significant qualifiers ---
    differing = differing_significant_qualifiers(a.qualifiers, b.qualifiers)
    if differing:
        return PrecheckResult(
            PrecheckOutcome.needs_adjudication,
            f"significant qualifier(s) differ: {', '.join(differing)}",
            {"differing_qualifiers": differing},
        )

    # --- value comparison ---
    if a.fact_kind == "status":
        na = normalize_value("status", a.value)
        nb = normalize_value("status", b.value)
        if na.state and na.state == nb.state:
            return _corroborates("same status")
        return PrecheckResult(
            PrecheckOutcome.needs_adjudication,
            "status values differ",
            {"state_a": na.state, "state_b": nb.state},
        )

    if a.fact_kind == "qualitative":
        return PrecheckResult(
            PrecheckOutcome.needs_adjudication,
            "qualitative claims need adjudication to compare",
        )

    na = normalize_value("quantitative", a.value)
    nb = normalize_value("quantitative", b.value)
    if not (na.comparable and nb.comparable):
        return PrecheckResult(
            PrecheckOutcome.needs_adjudication, "a value could not be normalized to an interval"
        )
    if na.dimension != nb.dimension:
        pair = {na.dimension, nb.dimension}
        if Dimension.unknown in pair:
            other = (pair - {Dimension.unknown}).pop()
            if other in _CONCRETE_DIMENSIONS:
                return PrecheckResult(
                    PrecheckOutcome.not_comparable,
                    f"one unit could not be classified, the other is {other}",
                    {"unit_a": a.value.get("unit"), "unit_b": b.value.get("unit")},
                )
            return PrecheckResult(
                PrecheckOutcome.needs_adjudication,
                "one unit could not be classified; adjudication needed to compare",
                {"unit_a": a.value.get("unit"), "unit_b": b.value.get("unit")},
            )
        return PrecheckResult(
            PrecheckOutcome.not_comparable,
            f"different dimensions ({na.dimension} vs {nb.dimension})",
        )
    if na.dimension is Dimension.unknown:
        return PrecheckResult(
            PrecheckOutcome.needs_adjudication,
            "neither unit could be classified; adjudication needed to compare",
            {"unit_a": a.value.get("unit"), "unit_b": b.value.get("unit")},
        )
    both_currency = na.dimension is Dimension.currency and nb.dimension is Dimension.currency
    if both_currency and na.currency and nb.currency and na.currency != nb.currency:
        return PrecheckResult(
            PrecheckOutcome.needs_adjudication,
            f"different currencies ({na.currency} vs {nb.currency})",
        )

    assert na.interval is not None and nb.interval is not None
    if na.interval.overlaps(nb.interval):
        return _corroborates(
            "value intervals overlap once units, comparator, and rounding are accounted for",
            {
                "interval_a": [na.interval.low, na.interval.high],
                "interval_b": [nb.interval.low, nb.interval.high],
            },
        )
    return PrecheckResult(
        PrecheckOutcome.needs_adjudication,
        "value intervals do not overlap",
        {
            "interval_a": [na.interval.low, na.interval.high],
            "interval_b": [nb.interval.low, nb.interval.high],
        },
    )

"""Currency, scale-word, and physical-unit parsing.

``parse_quantity(number, unit_text)`` returns the magnitude on a fixed base unit
for its dimension (currency -> major currency units, mass -> kilograms, length
-> metres, area -> square metres, percent -> a fraction, count -> ones) so two
facts written in different scales can be compared directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Dimension(StrEnum):
    currency = "currency"
    percent = "percent"
    mass = "mass"
    length = "length"
    area = "area"
    duration = "duration"
    count = "count"
    ratio = "ratio"
    unknown = "unknown"


@dataclass(frozen=True, slots=True)
class NormalizedQuantity:
    magnitude: float  # on the dimension's base unit
    dimension: Dimension
    currency: str | None = None
    base_unit: str = ""
    scale_word: str | None = None
    raw_unit: str = ""


# Indian and Western scale words -> multiplier
_SCALE_WORDS: dict[str, float] = {
    "hundred": 1e2,
    "thousand": 1e3,
    "k": 1e3,
    "lakh": 1e5,
    "lac": 1e5,
    "lakhs": 1e5,
    "million": 1e6,
    "millions": 1e6,
    "mn": 1e6,
    "mln": 1e6,
    "m": 1e6,
    "crore": 1e7,
    "crores": 1e7,
    "cr": 1e7,
    "billion": 1e9,
    "billions": 1e9,
    "bn": 1e9,
    "bln": 1e9,
    "b": 1e9,
    "trillion": 1e12,
    "tn": 1e12,
    "trn": 1e12,
}

_CURRENCY_TOKENS: dict[str, str] = {
    "₹": "INR",
    "rs": "INR",
    "rs.": "INR",
    "inr": "INR",
    "rupees": "INR",
    "rupee": "INR",
    "$": "USD",
    "us$": "USD",
    "usd": "USD",
    "dollars": "USD",
    "€": "EUR",
    "eur": "EUR",
    "euros": "EUR",
    "£": "GBP",
    "gbp": "GBP",
    "¥": "JPY",
    "jpy": "JPY",
}

# physical unit token -> (dimension, factor to base unit)
_PHYSICAL: dict[str, tuple[Dimension, float]] = {
    "kg": (Dimension.mass, 1.0),
    "kgs": (Dimension.mass, 1.0),
    "kilogram": (Dimension.mass, 1.0),
    "kilograms": (Dimension.mass, 1.0),
    "g": (Dimension.mass, 1e-3),
    "gram": (Dimension.mass, 1e-3),
    "grams": (Dimension.mass, 1e-3),
    "mg": (Dimension.mass, 1e-6),
    "t": (Dimension.mass, 1e3),
    "ton": (Dimension.mass, 1e3),
    "tons": (Dimension.mass, 1e3),
    "tonne": (Dimension.mass, 1e3),
    "tonnes": (Dimension.mass, 1e3),
    "mt": (Dimension.mass, 1e3),
    "lb": (Dimension.mass, 0.45359237),
    "lbs": (Dimension.mass, 0.45359237),
    "pound": (Dimension.mass, 0.45359237),
    "pounds": (Dimension.mass, 0.45359237),
    "m": (Dimension.length, 1.0),
    "metre": (Dimension.length, 1.0),
    "meter": (Dimension.length, 1.0),
    "metres": (Dimension.length, 1.0),
    "meters": (Dimension.length, 1.0),
    "km": (Dimension.length, 1e3),
    "kilometre": (Dimension.length, 1e3),
    "kilometer": (Dimension.length, 1e3),
    "cm": (Dimension.length, 1e-2),
    "mm": (Dimension.length, 1e-3),
    "mi": (Dimension.length, 1609.344),
    "mile": (Dimension.length, 1609.344),
    "miles": (Dimension.length, 1609.344),
    "ft": (Dimension.length, 0.3048),
    # area -> square metres. "square feet" / "sq ft" / "ft2" etc. are folded to
    # these canonical tokens by _normalize_area before tokenising.
    "sqm": (Dimension.area, 1.0),
    "sqcm": (Dimension.area, 1e-4),
    "sqkm": (Dimension.area, 1e6),
    "sqft": (Dimension.area, 0.09290304),
    "sqmi": (Dimension.area, 2_589_988.110336),
    "acre": (Dimension.area, 4046.8564224),
    "hectare": (Dimension.area, 10_000.0),
    "day": (Dimension.duration, 1.0),
    "days": (Dimension.duration, 1.0),
    "week": (Dimension.duration, 7.0),
    "weeks": (Dimension.duration, 7.0),
    "month": (Dimension.duration, 30.0),
    "months": (Dimension.duration, 30.0),
    "year": (Dimension.duration, 365.0),
    "years": (Dimension.duration, 365.0),
    "yr": (Dimension.duration, 365.0),
    "yrs": (Dimension.duration, 365.0),
    "hour": (Dimension.duration, 1 / 24),
    "hours": (Dimension.duration, 1 / 24),
    "hrs": (Dimension.duration, 1 / 24),
}

# Enumerable "things" -> count dimension. Still a closed list, but a broad one;
# anything not here lands in Dimension.unknown, and precheck now routes an
# unrecognised unit to adjudication rather than comparing it freely.
_COUNT_TOKENS = {
    "shipments",
    "parcels",
    "packages",
    "consignments",
    "deliveries",
    "pickups",
    "boxes",
    "cartons",
    "pallets",
    "containers",
    "units",
    "items",
    "pieces",
    "orders",
    "transactions",
    "trips",
    "routes",
    "lanes",
    "employees",
    "headcount",
    "staff",
    "personnel",
    "people",
    "passengers",
    "customers",
    "clients",
    "subscribers",
    "users",
    "accounts",
    "members",
    "stores",
    "outlets",
    "branches",
    "hubs",
    "warehouses",
    "facilities",
    "sites",
    "locations",
    "centres",
    "centers",
    "plants",
    "factories",
    "franchises",
    "dealers",
    "distributors",
    "partners",
    "cities",
    "towns",
    "districts",
    "countries",
    "markets",
    "trucks",
    "vehicles",
    "count",
    "nos",
    "no.",
    "x",
}

_PERCENT_TOKENS = {"%", "percent", "per cent", "pct", "percentage", "bps", "basis points"}
_TOKEN_RE = re.compile(r"[a-z%₹$€£¥.]+|[0-9]+")

# Area is written many ways ("square feet", "sq ft", "sq. ft.", "ft2", "ft²",
# "sqft"); fold each to one canonical token before tokenising so a single
# lookup in _PHYSICAL handles it. Order matters: km/cm/mi before the bare "m".
_AREA_SPELLINGS: list[tuple[str, str]] = [
    (r"kilomet(?:re|er)s?|kms?", "sqkm"),
    (r"centimet(?:re|er)s?|cms?", "sqcm"),
    (r"miles?|mi", "sqmi"),
    (r"feet|foot|ft", "sqft"),
    (r"met(?:re|er)s?|m", "sqm"),
]
_AREA_NORMALIZERS: list[tuple[re.Pattern[str], str]] = [
    *(
        (
            re.compile(rf"\bsq(?:uare)?\.?\s*(?:{names})\b|\b(?:{names})\s*[2²]\b"),
            f" {token} ",
        )
        for names, token in _AREA_SPELLINGS
    ),
    (re.compile(r"\bhectares?\b|\bha\b"), " hectare "),
    (re.compile(r"\bacres?\b"), " acre "),
]


def _normalize_area(text: str) -> str:
    for pattern, token in _AREA_NORMALIZERS:
        text = pattern.sub(token, text)
    return text


def _tokenize(unit_text: str) -> list[str]:
    text = unit_text.strip().lower()
    text = text.replace("per cent", "percent").replace("basis points", "bps")
    text = _normalize_area(text)
    return [t for t in _TOKEN_RE.findall(text) if t not in {".", "of", "the", "in", "a"}]


def parse_quantity(number: float, unit_text: str | None) -> NormalizedQuantity:
    raw = (unit_text or "").strip()
    tokens = _tokenize(raw)

    currency: str | None = None
    scale_word: str | None = None
    scale = 1.0
    dimension = Dimension.unknown
    physical_factor = 1.0
    physical_base = ""

    for tok in tokens:
        if tok in _CURRENCY_TOKENS and currency is None:
            currency = _CURRENCY_TOKENS[tok]
            dimension = Dimension.currency
        elif tok in _SCALE_WORDS:
            # chained scale words multiply: "lakh crore" = 1e5 * 1e7,
            # "thousand crore" = 1e3 * 1e7 (common in Indian macro reporting)
            scale_word = f"{scale_word} {tok}" if scale_word else tok
            scale *= _SCALE_WORDS[tok]
        elif tok in _PERCENT_TOKENS:
            dimension = Dimension.percent
            if tok in {"bps", "basis points"}:
                physical_factor = 1e-4
                physical_base = "fraction"
            else:
                physical_factor = 1e-2
                physical_base = "fraction"
        elif tok in _PHYSICAL and dimension in (Dimension.unknown, Dimension.currency):
            dim, factor = _PHYSICAL[tok]
            if dimension is Dimension.currency:
                # e.g. "$/kg" -- keep currency dimension, ignore the denominator
                continue
            dimension = dim
            physical_factor = factor
            physical_base = {
                Dimension.mass: "kg",
                Dimension.length: "m",
                Dimension.area: "m2",
                Dimension.duration: "day",
            }[dim]
        elif tok in _COUNT_TOKENS and dimension is Dimension.unknown:
            dimension = Dimension.count
            physical_base = "unit"

    if dimension is Dimension.unknown and scale_word is not None:
        dimension = Dimension.count
        physical_base = "unit"

    magnitude = number * scale * physical_factor
    base_unit = {
        Dimension.currency: currency or "",
        Dimension.percent: "fraction",
        Dimension.count: "unit",
        Dimension.ratio: "ratio",
        Dimension.unknown: "",
    }.get(dimension, physical_base)

    return NormalizedQuantity(
        magnitude=magnitude,
        dimension=dimension,
        currency=currency,
        base_unit=base_unit,
        scale_word=scale_word,
        raw_unit=raw,
    )

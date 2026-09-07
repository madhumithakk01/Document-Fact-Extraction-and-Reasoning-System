"""Build seed/snapshot.json from facts hand-verified against the source PDFs.

Every fact below carries a verbatim evidence quote taken from the dataset PDFs.
Run this to regenerate the curated demo snapshot; ``scripts.seed build``
regenerates it from a live pipeline run instead. ``scripts.seed load`` loads
whichever snapshot is on disk into the database.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "seed" / "snapshot.json"

DOCS = {
    "delhivery-filings": [
        {
            "ref": "d-deck",
            "filename": "delhivery-q4-fy24-earnings-presentation.pdf",
            "content_hash": "5ca307085c96c1fcbfd2d99a7ad40dcbd8958079b3833063520e4e84fdded2a8",
            "byte_size": 1988328,
            "content_type_detected": "slides",
            "page_count": 27,
        },
        {
            "ref": "d-ar",
            "filename": "delhivery-annual-report-fy24-excerpt.pdf",
            "content_hash": "de6d79adc0667d66f5415fa4fcec4b485a19073744adce44dfca3e34e529fa7a",
            "byte_size": 6679023,
            "content_type_detected": "mixed",
            "page_count": 100,
        },
    ],
    "india-macroeconomy": [
        {
            "ref": "m-imf",
            "filename": "imf-india-2025-article-iv-excerpt.pdf",
            "content_hash": "f6d3cfecafd9548920349b29b1137d645c20073434d0ac66485ead9738a0ea4d",
            "byte_size": 4305245,
            "content_type_detected": "mixed",
            "page_count": 95,
        },
        {
            "ref": "m-rbi",
            "filename": "rbi-annual-report-2024-25-excerpt.pdf",
            "content_hash": "73209a2caa2f5671f2feae065d01602302daaaac9e8230c9c471d99243fd079e",
            "byte_size": 1507769,
            "content_type_detected": "mixed",
            "page_count": 100,
        },
        {
            "ref": "m-survey",
            "filename": "india-economic-survey-2024-25-excerpt.pdf",
            "content_hash": "86f2e79a3b7b4a3698907897297b9e17fe06d39c074d52e68303066d18a2cf71",
            "byte_size": 3920928,
            "content_type_detected": "text_native",
            "page_count": 89,
        },
    ],
}


def q(number, unit, comparator="eq", number_high=None):
    v = {"comparator": comparator, "number": number, "unit": unit}
    if number_high is not None:
        v["number_high"] = number_high
    return v


def fact(
    ref,
    doc,
    entity,
    attribute,
    value,
    period,
    evidence,
    page,
    kind="quantitative",
    qualifiers=None,
    status="verified",
):
    return {
        "ref": ref,
        "document_ref": doc,
        "chunk_ref": "",
        "source_anchor": {},
        "page_number": page,
        "fact_kind": kind,
        "entity": entity,
        "entity_resolved": True,
        "attribute": attribute,
        "value": value,
        "period": {"raw_label": period},
        "qualifiers": qualifiers or {},
        "evidence_text": evidence,
        "verification_status": status,
        "extraction_confidence": 0.9,
        "verifier_confidence": 0.92,
        "notes": [],
    }


DELHIVERY_FACTS = [
    fact(
        "dl-1",
        "d-deck",
        "Delhivery",
        "FY24 consolidated EBITDA",
        q(127, "INR Crore"),
        "FY24",
        "FY24 EBITDA increased by Rs. 578 Cr to Rs. 127 Cr from Rs. (452 Cr) in FY23",
        5,
        qualifiers={"basis": "consolidated"},
    ),
    fact(
        "dl-2",
        "d-deck",
        "Delhivery",
        "FY23 consolidated EBITDA",
        q(-452, "INR Crore"),
        "FY23",
        "FY24 EBITDA increased by Rs. 578 Cr to Rs. 127 Cr from Rs. (452 Cr) in FY23",
        5,
    ),
    fact(
        "dl-3",
        "d-deck",
        "Delhivery",
        "FY24 EBITDA increase over FY23",
        q(578, "INR Crore"),
        "FY24",
        "FY24 EBITDA increased by Rs. 578 Cr to Rs. 127 Cr from Rs. (452 Cr) in FY23",
        5,
    ),
    fact(
        "dl-4",
        "d-deck",
        "Delhivery",
        "FY24 PAT loss reduction over FY23",
        q(759, "INR Crore"),
        "FY24",
        "PAT loss reduced by Rs. 759 Cr from Rs. (1,008 Cr) in FY23",
        5,
    ),
    fact(
        "dl-5",
        "d-deck",
        "Delhivery",
        "FY23 profit after tax",
        q(-1008, "INR Crore"),
        "FY23",
        "PAT loss reduced by Rs. 759 Cr from Rs. (1,008 Cr) in FY23",
        5,
    ),
    fact(
        "dl-6",
        "d-deck",
        "Delhivery PTL",
        "YoY revenue growth",
        q(30, "%", comparator="gt"),
        "FY24",
        "PTL: 30%+ YoY growth with significant improvement in profitability and market share",
        5,
    ),
    fact(
        "dl-7",
        "d-deck",
        "Delhivery Express Parcel",
        "service EBITDA profitability",
        q(18, "%", comparator="gt"),
        "FY24",
        "Express Parcel: 18%+ Service EBITDA profitability; robust growth in key segments",
        5,
    ),
    fact(
        "dl-8",
        "d-deck",
        "Delhivery TL",
        "YoY revenue growth",
        q(40, "%"),
        "FY24",
        "TL: 40% YoY revenue growth with service EBITDA profitability improvement",
        5,
    ),
    fact(
        "dl-9",
        "d-deck",
        "Delhivery",
        "net working capital days",
        q(38, "days"),
        "FY23",
        "Sharp YoY reduction in NWC days from 38 to 31 days",
        5,
    ),
    fact(
        "dl-10",
        "d-deck",
        "Delhivery",
        "net working capital days",
        q(31, "days"),
        "FY24",
        "Sharp YoY reduction in NWC days from 38 to 31 days",
        5,
    ),
    fact(
        "dl-11",
        "d-deck",
        "Delhivery SCS",
        "service EBITDA profitability",
        {"text": "doubled over FY23"},
        "FY24",
        "SCS: Doubled service EBITDA profitability over FY23, strong Q4",
        5,
        kind="qualitative",
    ),
    fact(
        "dl-12",
        "d-deck",
        "Delhivery",
        "FY24 revenue from services",
        q(8142, "INR Crore"),
        "FY24",
        "₹8,142 Cr FY24 revenue from services",
        6,
    ),
    fact(
        "dl-13",
        "d-deck",
        "Delhivery",
        "express parcel shipments",
        q(740, "million"),
        "FY24",
        "740 Mn Express parcel shipments in FY24",
        6,
    ),
    fact(
        "dl-14",
        "d-deck",
        "Delhivery",
        "FY24 EBITDA margin",
        q(1.6, "%"),
        "FY24",
        "₹127Cr / 1.6% EBITDA / EBITDA margin",
        6,
    ),
    fact(
        "dl-15",
        "d-ar",
        "Delhivery",
        "FY24 consolidated EBITDA",
        q(1266, "INR million"),
        "FY24",
        "EBITDA (₹ million) and EBITDA margin (%) FY20 FY21 FY22 FY23 FY24 ... 1,266",
        6,
        qualifiers={
            "basis": "consolidated",
            "column_header": "FY24",
            "row_header": "EBITDA (INR million)",
        },
    ),
    fact(
        "dl-16",
        "d-ar",
        "Delhivery",
        "FY24 revenue from services",
        q(81415, "INR million"),
        "FY24",
        "Revenue from services (₹ million) 72,236 FY23 70,536 FY22 81,415 FY24",
        6,
        qualifiers={"column_header": "FY24", "row_header": "Revenue from services (INR million)"},
    ),
    fact(
        "dl-17",
        "d-ar",
        "Delhivery",
        "part-truckload tonnage",
        q(1429, "thousand tonnes"),
        "FY24",
        "Part-truckload tonnage (thousand tonnes) FY20 FY21 FY22 FY23 FY24 ... 1,429",
        6,
        qualifiers={"column_header": "FY24"},
    ),
    fact(
        "dl-18",
        "d-ar",
        "Delhivery",
        "net working capital days",
        q(31, "days"),
        "FY24",
        "Net working capital days 73 47 37 38 31 FY20 FY21 FY22 FY23 FY24",
        6,
        qualifiers={"column_header": "FY24"},
    ),
    fact(
        "dl-19",
        "d-ar",
        "Delhivery",
        "FY24 profit after tax",
        q(-2492, "INR million"),
        "FY24",
        "Profit after tax (₹ million) (2,689) (4,157) (10,808) (10,078) (2,492)",
        6,
        qualifiers={"column_header": "FY24"},
    ),
]

DELHIVERY_RELS = [
    {
        "fact_a_ref": "dl-1",
        "fact_b_ref": "dl-15",
        "relationship_type": "corroborates",
        "reconciliation_basis": None,
        "explanation": "Same figure in different units: Rs. 127 Cr equals about "
        "Rs. 1,270 million, which agrees with the annual report's Rs. 1,266 million once "
        "rounding is allowed. Both are FY24 consolidated EBITDA.",
        "confidence": 0.95,
        "investigation_trail": [
            {
                "step": 0,
                "method": "deterministic_precheck",
                "detail": {
                    "interval_a": [1265000000.0, 1275000000.0],
                    "interval_b": [1265500000.0, 1266500000.0],
                },
            }
        ],
    },
    {
        "fact_a_ref": "dl-12",
        "fact_b_ref": "dl-16",
        "relationship_type": "corroborates",
        "reconciliation_basis": None,
        "explanation": "Rs. 8,142 Cr equals Rs. 81,420 million, matching the annual report's "
        "Rs. 81,415 million FY24 revenue from services within rounding.",
        "confidence": 0.95,
        "investigation_trail": [{"step": 0, "method": "deterministic_precheck"}],
    },
    {
        "fact_a_ref": "dl-10",
        "fact_b_ref": "dl-18",
        "relationship_type": "corroborates",
        "reconciliation_basis": None,
        "explanation": "The earnings deck and the annual report both report FY24 net working "
        "capital days as 31.",
        "confidence": 0.96,
        "investigation_trail": [{"step": 0, "method": "deterministic_precheck"}],
    },
]

DELHIVERY_CONCEPTS = [
    {
        "kind": "attribute",
        "canonical_name": "consolidated EBITDA",
        "raw_aliases": [
            "FY24 consolidated EBITDA",
            "FY23 consolidated EBITDA",
            "EBITDA (INR million)",
        ],
        "first_seen_document_ref": "d-deck",
    },
    {
        "kind": "attribute",
        "canonical_name": "revenue from services",
        "raw_aliases": ["FY24 revenue from services", "Revenue from services (INR million)"],
        "first_seen_document_ref": "d-deck",
    },
    {
        "kind": "attribute",
        "canonical_name": "net working capital days",
        "raw_aliases": ["NWC days", "net working capital days"],
        "first_seen_document_ref": "d-deck",
    },
    {
        "kind": "entity",
        "canonical_name": "Delhivery",
        "raw_aliases": ["Delhivery", "the Company"],
        "first_seen_document_ref": "d-deck",
    },
]

MACRO_FACTS = [
    fact(
        "mm-1",
        "m-imf",
        "India",
        "real GDP growth",
        q(6.5, "%"),
        "FY2024/25",
        "Following economic growth of 6.5 percent in FY2024/25, real GDP expanded by 7.8 percent "
        "in the first quarter of FY2025/26",
        3,
        qualifiers={"asserting_party": "IMF"},
    ),
    fact(
        "mm-2",
        "m-imf",
        "India",
        "real GDP growth (Q1)",
        q(7.8, "%"),
        "Q1 FY2025/26",
        "real GDP expanded by 7.8 percent in the first quarter of FY2025/26",
        3,
        qualifiers={"asserting_party": "IMF"},
    ),
    fact(
        "mm-3",
        "m-imf",
        "India",
        "real GDP growth",
        q(6.6, "%"),
        "FY2025/26",
        "real GDP is projected to grow at 6.6 percent in FY2025/26 before moderating to 6.2 "
        "percent in FY2026/27",
        3,
        qualifiers={"asserting_party": "IMF", "forecast_vs_actual": "forecast"},
    ),
    fact(
        "mm-4",
        "m-imf",
        "India",
        "real GDP growth",
        q(6.2, "%"),
        "FY2026/27",
        "before moderating to 6.2 percent in FY2026/27",
        3,
        qualifiers={"asserting_party": "IMF", "forecast_vs_actual": "forecast"},
    ),
    fact(
        "mm-5",
        "m-imf",
        "India",
        "real GDP growth (at market prices)",
        q(6.5, "%"),
        "2024/25",
        "Real GDP (at market prices) 9.7 7.6 9.2 6.5 6.6 6.2",
        5,
        qualifiers={
            "asserting_party": "IMF",
            "column_header": "2024/25",
            "row_header": "Real GDP (at market prices)",
        },
    ),
    fact(
        "mm-6",
        "m-imf",
        "India",
        "real GDP growth (at market prices)",
        q(6.6, "%"),
        "2025/26",
        "Real GDP (at market prices) 9.7 7.6 9.2 6.5 6.6 6.2",
        5,
        qualifiers={
            "asserting_party": "IMF",
            "column_header": "2025/26",
            "row_header": "Real GDP (at market prices)",
        },
    ),
    fact(
        "mm-7",
        "m-imf",
        "India",
        "consumer price inflation (combined)",
        q(4.6, "%"),
        "2024/25",
        "Consumer prices - Combined 5.5 6.7 5.4 4.6 2.8 4.0",
        5,
        qualifiers={"asserting_party": "IMF", "column_header": "2024/25"},
    ),
    fact(
        "mm-8",
        "m-imf",
        "India",
        "consumer price inflation (combined)",
        q(2.8, "%"),
        "2025/26",
        "Consumer prices - Combined 5.5 6.7 5.4 4.6 2.8 4.0",
        5,
        qualifiers={"asserting_party": "IMF", "column_header": "2025/26"},
    ),
    fact(
        "mm-9",
        "m-imf",
        "India (central government)",
        "overall balance",
        q(-4.9, "% of GDP"),
        "2024/25",
        "Central government overall balance -6.7 -6.6 -5.5 -4.9 -4.5 -4.5",
        5,
        qualifiers={"asserting_party": "IMF", "column_header": "2024/25"},
    ),
    fact(
        "mm-10",
        "m-imf",
        "India (general government)",
        "overall balance",
        q(-7.9, "% of GDP"),
        "2024/25",
        "General government overall balance -9.4 -9.0 -8.1 -7.9 -7.1 -7.2",
        5,
        qualifiers={"asserting_party": "IMF", "column_header": "2024/25"},
    ),
    fact(
        "mm-11",
        "m-rbi",
        "India (central government)",
        "gross fiscal deficit",
        q(4.7, "% of GDP"),
        "2024-25",
        "gross fiscal deficit (GFD) declining to 4.7 per cent of GDP in 2024-25 [revised "
        "estimates (RE)] from 5.5 per cent of GDP in 2023-24",
        11,
        qualifiers={"asserting_party": "RBI", "forecast_vs_actual": "revised estimate"},
    ),
    fact(
        "mm-12",
        "m-rbi",
        "India (central government)",
        "gross fiscal deficit",
        q(5.5, "% of GDP"),
        "2023-24",
        "declining to 4.7 per cent of GDP in 2024-25 ... from 5.5 per cent of GDP in 2023-24",
        11,
        qualifiers={"asserting_party": "RBI"},
    ),
    fact(
        "mm-13",
        "m-rbi",
        "India",
        "gross tax receipts growth",
        q(11.2, "%"),
        "2024-25",
        "gross-tax and non-tax receipts recorded resilient growth of 11.2 per cent and 32.2 per "
        "cent, respectively, in 2024-25 (RE)",
        11,
        qualifiers={"asserting_party": "RBI"},
    ),
    fact(
        "mm-14",
        "m-rbi",
        "India",
        "foreign exchange reserves",
        q(668.3, "USD billion"),
        "end-March 2025",
        "ample forex reserves at US$ 668.3 billion (as at end-March 2025), "
        "covering 11 months of merchandise imports",
        12,
        qualifiers={"asserting_party": "RBI"},
    ),
    fact(
        "mm-15",
        "m-survey",
        "United States",
        "real GDP growth",
        q(2.8, "%"),
        "2024",
        "Growth in the US is expected to remain strong at 2.8 per cent in 2024 and may decline "
        "slightly in 2025",
        6,
        qualifiers={"asserting_party": "Economic Survey"},
    ),
    fact(
        "mm-16",
        "m-survey",
        "Euro area",
        "real GDP growth",
        q(0.8, "%"),
        "2024",
        "growth is expected to improve from 0.4 per cent in 2023 to 0.8 per cent in 2024 and "
        "further to 1.0 per cent in 2025",
        6,
        qualifiers={"asserting_party": "Economic Survey"},
    ),
]

MACRO_RELS = [
    {
        "fact_a_ref": "mm-1",
        "fact_b_ref": "mm-5",
        "relationship_type": "corroborates",
        "reconciliation_basis": None,
        "explanation": "The IMF press release states FY2024/25 real GDP growth of 6.5%, and the "
        "IMF's own Selected Indicators table reports the same 6.5% for 2024/25. Prose and table "
        "agree.",
        "confidence": 0.97,
        "investigation_trail": [{"step": 0, "method": "deterministic_precheck"}],
    },
    {
        "fact_a_ref": "mm-11",
        "fact_b_ref": "mm-9",
        "relationship_type": "reconciled_by_context",
        "reconciliation_basis": "gross fiscal deficit vs overall balance; revised estimate vs "
        "projection",
        "explanation": "RBI reports a 2024-25 gross fiscal deficit of 4.7% of GDP (revised "
        "estimates), while the IMF reports a 2024/25 central government overall balance of "
        "-4.9% of GDP. The small gap is explained by the different measures (gross fiscal "
        "deficit excludes some items captured in the overall balance) and the RBI figure being "
        "a revised estimate against the IMF projection.",
        "confidence": 0.78,
        "investigation_trail": [
            {
                "step": 0,
                "method": "deterministic_precheck",
                "reason": "significant qualifier(s) differ: asserting_party",
            },
            {
                "step": 1,
                "action": "final_classification",
                "verdict": "reconciled_by_context",
                "basis": "gross fiscal deficit vs overall balance",
                "budget_exhausted": False,
            },
        ],
    },
]

MACRO_CONCEPTS = [
    {
        "kind": "attribute",
        "canonical_name": "real GDP growth",
        "raw_aliases": [
            "real GDP growth",
            "real GDP growth (at market prices)",
            "Real GDP (at market prices)",
        ],
        "first_seen_document_ref": "m-imf",
    },
    {
        "kind": "attribute",
        "canonical_name": "consumer price inflation",
        "raw_aliases": [
            "consumer price inflation (combined)",
            "Consumer prices - Combined",
            "headline inflation",
        ],
        "first_seen_document_ref": "m-imf",
    },
    {
        "kind": "attribute",
        "canonical_name": "central government fiscal deficit",
        "raw_aliases": ["gross fiscal deficit", "central government overall balance", "GFD"],
        "first_seen_document_ref": "m-imf",
    },
    {
        "kind": "entity",
        "canonical_name": "India",
        "raw_aliases": ["India", "India (central government)", "India (general government)"],
        "first_seen_document_ref": "m-imf",
    },
]


def _domain_profile(doc_refs):
    return {
        "centroid_embedding": None,
        "sub_clusters": [
            {"id": "sc_1", "centroid": [], "document_ids": list(doc_refs), "size": len(doc_refs)}
        ],
        "vocabulary": [],
        "document_count": len(doc_refs),
    }


snapshot = {
    "projects": [
        {
            "name": "delhivery-filings",
            "domain_profile": _domain_profile(["d-deck", "d-ar"]),
            "documents": DOCS["delhivery-filings"],
            "chunks": [],
            "facts": DELHIVERY_FACTS,
            "relationships": DELHIVERY_RELS,
            "concepts": DELHIVERY_CONCEPTS,
        },
        {
            "name": "india-macroeconomy",
            "domain_profile": _domain_profile(["m-imf", "m-rbi", "m-survey"]),
            "documents": DOCS["india-macroeconomy"],
            "chunks": [],
            "facts": MACRO_FACTS,
            "relationships": MACRO_RELS,
            "concepts": MACRO_CONCEPTS,
        },
    ]
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
n = sum(len(p["facts"]) for p in snapshot["projects"])
r = sum(len(p["relationships"]) for p in snapshot["projects"])
print(f"wrote {OUT} — 2 projects, {n} facts, {r} relationships")

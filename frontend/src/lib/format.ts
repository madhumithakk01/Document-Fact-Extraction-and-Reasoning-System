import type { Fact, FactValue } from "@/api/types";

const COMPARATOR_SIGN: Record<string, string> = {
  eq: "",
  approx: "≈ ",
  gt: "> ",
  gte: "≥ ",
  lt: "< ",
  lte: "≤ ",
  range: "",
};

export function formatValue(v: FactValue, kind: Fact["fact_kind"]): string {
  if (kind === "status") return v.state ?? "—";
  if (kind === "qualitative") return v.text ?? "—";
  if (v.number == null && v.number_high == null) return "—";
  // An unspecified comparator renders as approximate ("~"), never as an inferred
  // exact value the extractor did not assert. Found during review.
  const comparator = v.comparator ?? "unspecified";
  const sign = comparator === "unspecified" ? "~ " : COMPARATOR_SIGN[comparator] ?? "";
  const num =
    comparator === "range" && v.number_high != null
      ? `${fmtNum(v.number)}–${fmtNum(v.number_high)}`
      : fmtNum(v.number ?? v.number_high);
  return `${sign}${num}${v.unit ? ` ${v.unit}` : ""}`.trim();
}

function fmtNum(n: number | null | undefined): string {
  if (n == null) return "—";
  if (Math.abs(n) >= 1000) return n.toLocaleString("en-IN");
  return String(n);
}

export function periodLabel(fact: Fact): string {
  return fact.period.raw_label ?? "—";
}

/** Deterministic hue from a string, for entity monogram tints. */
export function hashHue(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h) % 360;
}

export function initials(s: string): string {
  const parts = s.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "·";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

import type { RelationshipType, VerificationStatus } from "@/api/types";

// Every semantic colour is paired with a text label -- colour is reinforcement,
// never the only signal (UI_DESIGN.md).

export const RELATIONSHIP_META: Record<
  RelationshipType,
  { label: string; className: string; dot: string }
> = {
  corroborates: {
    label: "Corroborated",
    className: "text-corroborates border-corroborates/40",
    dot: "bg-corroborates",
  },
  contradicts: {
    label: "Contradiction",
    className: "text-contradicts border-contradicts/40",
    dot: "bg-contradicts",
  },
  reconciled_by_context: {
    label: "Reconciled",
    className: "text-reconciled border-reconciled/40",
    dot: "bg-reconciled",
  },
  unrelated: {
    label: "Unrelated",
    className: "text-text-muted border-hairline",
    dot: "bg-text-muted",
  },
};

export const STATUS_META: Record<
  VerificationStatus,
  { label: string; className: string }
> = {
  verified: { label: "Verified", className: "text-corroborates border-corroborates/40" },
  auto_corrected: { label: "Auto-corrected", className: "text-reconciled border-reconciled/40" },
  needs_review: { label: "Needs review", className: "text-review border-review/50" },
  rejected: { label: "Rejected", className: "text-contradicts border-contradicts/40" },
  pending: { label: "Pending", className: "text-text-muted border-hairline" },
};

// Silent assumptions the pipeline made to fill a gap the source left open. Each
// one lowers the fact's extraction confidence and is shown next to the fact.
export const ASSUMPTION_LABELS: Record<string, string> = {
  fy_convention_assumed: "FY convention assumed",
  entity_inferred: "Entity inferred",
  comparator_unspecified: "Comparator not stated",
};

export function factAssumptions(qualifiers: Record<string, string | string[]>): string[] {
  const a = qualifiers?.assumed;
  return Array.isArray(a) ? a : [];
}

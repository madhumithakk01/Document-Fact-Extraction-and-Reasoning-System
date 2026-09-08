// Response shapes from the FastAPI backend (app/api/schemas.py).

export interface Project {
  project_id: string;
  name: string;
  created_at: string;
  domain_profile: Record<string, unknown>;
}

export interface ProjectSummary extends Project {
  document_count: number;
  fact_count: number;
  facts_by_status: Record<string, number>;
  relationship_count: number;
  relationships_by_type: Record<string, number>;
  concept_count: number;
  sub_cluster_count: number;
}

export type ProcessingStatus =
  | "queued"
  | "extracting"
  | "partially_ready"
  | "verifying"
  | "comparing"
  | "ready"
  | "failed"
  | "pending";

export interface DocumentOut {
  document_id: string;
  project_id: string;
  filename: string;
  content_hash: string;
  byte_size: number;
  content_type_detected: string;
  processing_status: ProcessingStatus;
  processing_error: string | null;
  processing_detail: string | null;
  pages_total: number | null;
  pages_processed: number | null;
  page_count: number;
  ocr_page_count: number;
  routing_profile: Record<string, unknown>;
  sub_cluster_id: string | null;
  off_domain: boolean;
  uploaded_at: string | null;
  created_at: string;
}

export interface DocumentStatus {
  document_id: string;
  processing_status: ProcessingStatus;
  processing_error: string | null;
  processing_detail: string | null;
  pages_total: number | null;
  pages_processed: number | null;
  page_count: number;
  chunk_count: number;
  fact_count: number;
  facts_by_status: Record<string, number>;
  relationship_count: number;
}

export type FactKind = "quantitative" | "status" | "qualitative";
export type VerificationStatus =
  | "pending"
  | "verified"
  | "auto_corrected"
  | "needs_review"
  | "rejected";

export interface FactValue {
  comparator?: string | null;
  number?: number | null;
  number_high?: number | null;
  unit?: string | null;
  state?: string | null;
  text?: string | null;
}

export interface FactPeriod {
  raw_label?: string | null;
  start_date?: string | null;
  end_date?: string | null;
}

export interface Fact {
  fact_id: string;
  project_id: string;
  document_id: string;
  chunk_id: string | null;
  page_number: number | null;
  fact_kind: FactKind;
  entity: string;
  entity_resolved: boolean;
  attribute: string;
  value: FactValue;
  period: FactPeriod;
  qualifiers: Record<string, string>;
  evidence_text: string;
  verification_status: VerificationStatus;
  extraction_confidence: number;
  verifier_confidence: number | null;
  notes: unknown[];
  source_anchor: Record<string, unknown>;
  created_at: string;
}

export interface BBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface Evidence {
  fact_id: string;
  document_id: string;
  filename: string;
  page_number: number | null;
  evidence_text: string;
  surrounding_text: string;
  page_image_url: string | null;
  page_width: number | null;
  page_height: number | null;
  highlight_bboxes: BBox[];
  highlight_bboxes_normalized: BBox[];
}

export type RelationshipType =
  | "corroborates"
  | "contradicts"
  | "reconciled_by_context"
  | "unrelated";

export interface Relationship {
  relationship_id: string;
  project_id: string;
  fact_a_id: string;
  fact_b_id: string;
  relationship_type: RelationshipType;
  reconciliation_basis: string | null;
  explanation: string;
  confidence: number;
  investigation_trail: unknown[];
  created_at: string;
}

export interface RelationshipDetail extends Relationship {
  fact_a: Fact;
  fact_b: Fact;
}

export interface Concept {
  concept_id: string;
  kind: "entity" | "attribute";
  canonical_name: string;
  raw_aliases: string[];
  first_seen_document_id: string | null;
  first_seen_at: string | null;
}

export interface OntologyGroup {
  document_id: string | null;
  document_filename: string | null;
  concepts: Concept[];
}

export interface Ontology {
  groups: OntologyGroup[];
}

export interface DocumentEvaluation {
  document_id: string;
  filename: string;
  processed_at: string | null;
  facts_total: number;
  facts_by_status: Record<string, number>;
  grounding_checks: number;
  grounding_pass: number;
  grounding_pass_rate: number;
}

export interface TimelinePoint {
  index: number;
  document_id: string;
  filename: string;
  cumulative_facts: number;
  grounding_pass_rate: number;
  verified_rate: number;
  needs_review_rate: number;
}

export interface Evaluation {
  grounding_checks: number;
  grounding_pass: number;
  grounding_pass_rate: number;
  independent_verify_calls: number;
  independent_verify_breakdown: Record<string, number>;
  facts_total: number;
  facts_by_status: Record<string, number>;
  verified_rate: number;
  auto_correction_rate: number;
  needs_review_rate: number;
  rejected_rate: number;
  per_document: DocumentEvaluation[];
  timeline: TimelinePoint[];
}

export interface QueryCitation {
  marker: string;
  fact_id: string;
  entity: string;
  attribute: string;
  value_summary: string;
  period: string | null;
  verification_status: string;
  document_filename: string;
  page_number: number | null;
  evidence_text: string;
}

export interface QueryDisagreement {
  relationship_type: "contradicts" | "reconciled_by_context";
  reconciliation_basis: string | null;
  explanation: string;
  marker_a: string;
  marker_b: string;
  fact_a_id: string;
  fact_b_id: string;
  fact_a_summary: string;
  fact_b_summary: string;
}

export interface QueryTraceEntry {
  step: number;
  tool: string;
  args: Record<string, unknown>;
  rationale: string;
  result: string;
}

export interface QueryResult {
  question: string;
  answer: string;
  citations: QueryCitation[];
  disagreements: QueryDisagreement[];
  trace: QueryTraceEntry[];
  fact_ids_considered: string[];
  tool_calls_used: number;
}

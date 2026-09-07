import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/api/client";
import { EmptyState, ErrorState, Spinner } from "@/components/common";
import type { Fact, Relationship, RelationshipDetail } from "@/api/types";
import { formatValue } from "@/lib/format";
import { RELATIONSHIP_META } from "@/lib/semantic";
import { useUi } from "@/state/ui";

export function RelationshipsView({ projectId }: { projectId: string }) {
  const [type, setType] = useState("");
  const rels = useQuery({
    queryKey: ["relationships", projectId, type],
    queryFn: () => api.listRelationships(projectId, { type: type || undefined }),
  });

  return (
    <div className="flex h-full flex-col">
      <div className="flex gap-2 border-b border-hairline px-6 py-3">
        <select
          value={type}
          onChange={(e) => setType(e.target.value)}
          className="rounded border border-hairline bg-raised px-2 py-1 text-cell text-text-primary"
        >
          {["", "corroborates", "contradicts", "reconciled_by_context", "unrelated"].map(
            (o) => (
              <option key={o} value={o}>
                {o ? RELATIONSHIP_META[o as keyof typeof RELATIONSHIP_META].label : "all types"}
              </option>
            ),
          )}
        </select>
        <span className="ml-auto self-center text-meta text-text-muted">
          {rels.data?.length ?? 0} relationship{rels.data?.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-6">
        {rels.isLoading && <Spinner />}
        {rels.error && <ErrorState message={String(rels.error)} />}
        {rels.data?.length === 0 && (
          <EmptyState
            title="No relationships yet"
            hint="Once two or more documents have facts about the same thing, corroborations, contradictions, and reconciliations show up here."
          />
        )}
        <div className="flex flex-col gap-3">
          {rels.data?.map((r) => (
            <RelationshipRow key={r.relationship_id} projectId={projectId} rel={r} />
          ))}
        </div>
      </div>
    </div>
  );
}

function RelationshipRow({
  projectId,
  rel,
}: {
  projectId: string;
  rel: Relationship;
}) {
  const [open, setOpen] = useState(false);
  const meta = RELATIONSHIP_META[rel.relationship_type];
  const detail = useQuery({
    queryKey: ["relationship", rel.relationship_id],
    queryFn: () => api.getRelationship(projectId, rel.relationship_id),
    enabled: open,
  });
  const { openEvidence } = useUi();

  return (
    <div className="rounded border border-hairline bg-recessed p-3">
      <div className="flex flex-wrap items-center gap-2">
        <FactChip projectId={projectId} factId={rel.fact_a_id} onClick={() => openEvidence(rel.fact_a_id)} />
        <button
          onClick={() => setOpen((o) => !o)}
          className={`flex items-center gap-2 border-y px-3 py-1 text-meta ${meta.className}`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
          {meta.label}
          {rel.reconciliation_basis && (
            <span className="text-text-muted">· {rel.reconciliation_basis}</span>
          )}
          <span className="text-text-muted">{open ? "▾" : "▸"}</span>
        </button>
        <FactChip projectId={projectId} factId={rel.fact_b_id} onClick={() => openEvidence(rel.fact_b_id)} />
        <span className="ml-auto font-mono text-meta text-text-muted">
          {(rel.confidence * 100).toFixed(0)}%
        </span>
      </div>

      {open && (
        <div className="mt-3 border-t border-hairline pt-3 text-cell text-text-primary">
          {detail.isLoading && <Spinner />}
          {detail.data && (
            <TrailDetail detail={detail.data} onFact={(id) => openEvidence(id)} />
          )}
        </div>
      )}
    </div>
  );
}

function TrailDetail({
  detail,
  onFact,
}: {
  detail: RelationshipDetail;
  onFact: (id: string) => void;
}) {
  const trail = Array.isArray(detail.investigation_trail)
    ? (detail.investigation_trail as Record<string, unknown>[])
    : [];
  return (
    <>
      <p className="max-w-[70ch] leading-relaxed">{detail.explanation}</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <FullFact fact={detail.fact_a} onClick={() => onFact(detail.fact_a.fact_id)} />
        <FullFact fact={detail.fact_b} onClick={() => onFact(detail.fact_b.fact_id)} />
      </div>
      {trail.length > 0 && (
        <div className="mt-3">
          <p className="text-meta text-text-muted">Investigation</p>
          <ol className="mt-1 list-decimal space-y-1 pl-5 text-meta text-text-muted">
            {trail.map((step, i) => (
              <li key={i}>
                {step.method
                  ? `${step.method}${step.reason ? ` — ${step.reason}` : ""}`
                  : step.tool
                    ? `${step.tool}(${JSON.stringify(step.args ?? {})}) — ${String(
                        step.rationale ?? "",
                      )}`
                    : step.action
                      ? `${step.action}${step.verdict ? `: ${step.verdict}` : ""}`
                      : JSON.stringify(step)}
              </li>
            ))}
          </ol>
        </div>
      )}
    </>
  );
}

function FullFact({ fact, onClick }: { fact: Fact; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="rounded border border-hairline bg-raised px-2.5 py-2 text-left text-meta hover:border-accent-dim"
    >
      <div className="text-text-primary">{fact.entity}</div>
      <div className="text-text-muted">{fact.attribute}</div>
      <div className="mt-0.5 font-mono text-text-primary">
        {formatValue(fact.value, fact.fact_kind)} · {fact.period.raw_label ?? "—"}
      </div>
      <div className="mt-1 line-clamp-2 italic text-text-muted">
        “{fact.evidence_text}”
      </div>
    </button>
  );
}

function FactChip({
  projectId,
  factId,
  onClick,
}: {
  projectId: string;
  factId: string;
  onClick: () => void;
}) {
  const fact = useQuery({
    queryKey: ["fact", factId],
    queryFn: () => api.getFact(projectId, factId),
    staleTime: 60_000,
  });
  const label = fact.data
    ? `${fact.data.entity} · ${formatValue(fact.data.value, fact.data.fact_kind)}`
    : factId.slice(0, 8);
  return (
    <button
      onClick={onClick}
      title={fact.data ? fact.data.attribute : factId}
      className="max-w-[16rem] truncate rounded border border-hairline bg-raised px-2 py-1 font-mono text-meta text-text-muted hover:border-accent-dim hover:text-text-primary"
    >
      {label}
    </button>
  );
}

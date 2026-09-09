import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "@/api/client";
import { Badge } from "@/components/Badge";
import { EmptyState, ErrorState, Spinner } from "@/components/common";
import { Monogram } from "@/components/Monogram";
import type { Fact } from "@/api/types";
import { formatValue, periodLabel } from "@/lib/format";
import { ASSUMPTION_LABELS, STATUS_META, factAssumptions } from "@/lib/semantic";
import { useUi } from "@/state/ui";

type SortKey = "entity" | "attribute" | "value" | "period" | "status";

export function FactsView({ projectId }: { projectId: string }) {
  const { evidenceFactId, openEvidence } = useUi();
  const [filters, setFilters] = useState({
    entity: "",
    attribute: "",
    fact_kind: "",
    verification_status: "",
  });
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({
    key: "entity",
    dir: 1,
  });

  const facts = useQuery({
    queryKey: ["facts", projectId, filters],
    queryFn: () =>
      api.listFacts(projectId, {
        entity: filters.entity || undefined,
        attribute: filters.attribute || undefined,
        fact_kind: filters.fact_kind || undefined,
        verification_status: filters.verification_status || undefined,
        limit: "1000",
      }),
  });

  const rows = useMemo(() => {
    const data = [...(facts.data ?? [])];
    const dir = sort.dir;
    data.sort((a, b) => dir * keyOf(a, sort.key).localeCompare(keyOf(b, sort.key)));
    return data;
  }, [facts.data, sort]);

  const ids = useMemo(() => rows.map((f) => f.fact_id), [rows]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap gap-2 border-b border-hairline px-6 py-3">
        <FilterInput
          placeholder="entity"
          value={filters.entity}
          onChange={(v) => setFilters((f) => ({ ...f, entity: v }))}
        />
        <FilterInput
          placeholder="attribute"
          value={filters.attribute}
          onChange={(v) => setFilters((f) => ({ ...f, attribute: v }))}
        />
        <FilterSelect
          value={filters.fact_kind}
          onChange={(v) => setFilters((f) => ({ ...f, fact_kind: v }))}
          options={["", "quantitative", "status", "qualitative"]}
        />
        <FilterSelect
          value={filters.verification_status}
          onChange={(v) => setFilters((f) => ({ ...f, verification_status: v }))}
          options={["", "verified", "auto_corrected", "needs_review", "rejected", "pending"]}
        />
        <span className="ml-auto self-center text-meta text-text-muted">
          {rows.length} fact{rows.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {facts.isLoading && <div className="p-6"><Spinner /></div>}
        {facts.error && <ErrorState message={String(facts.error)} />}
        {facts.data?.length === 0 && (
          <EmptyState
            title="No facts yet"
            hint="Upload and process a document, then its facts appear here. Click any row to see the exact source."
          />
        )}

        {rows.length > 0 && (
          <table className="w-full border-collapse text-cell">
            <thead className="sticky top-0 z-[1] bg-canvas">
              <tr className="border-b border-hairline text-left text-meta text-text-muted">
                <Th onClick={() => toggle(setSort, "entity")}>Entity</Th>
                <Th onClick={() => toggle(setSort, "attribute")}>Attribute</Th>
                <Th className="text-right" onClick={() => toggle(setSort, "value")}>
                  Value
                </Th>
                <Th onClick={() => toggle(setSort, "period")}>Period</Th>
                <Th onClick={() => toggle(setSort, "status")}>Status</Th>
                <th className="py-2 pr-4 font-medium">Source</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((f) => {
                const st = STATUS_META[f.verification_status];
                const assumed = factAssumptions(f.qualifiers);
                const correctedFields = f.corrections.flatMap((c) => Object.keys(c.changes));
                return (
                  <tr
                    key={f.fact_id}
                    onClick={() => openEvidence(f.fact_id, ids)}
                    className={`cursor-pointer border-b border-hairline hover:bg-raised ${
                      f.fact_id === evidenceFactId ? "bg-raised" : ""
                    }`}
                  >
                    <td className="py-1.5 pl-4 pr-3">
                      <span className="flex items-center gap-2">
                        <Monogram name={f.entity} />
                        <span className="truncate">{f.entity}</span>
                        {!f.entity_resolved && (
                          <span
                            title="entity inferred from carried context"
                            className="text-text-muted"
                          >
                            ~
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="max-w-[16rem] truncate py-1.5 pr-3 text-text-primary">
                      {f.attribute}
                    </td>
                    <td className="whitespace-nowrap py-1.5 pr-3 text-right font-mono tabular-nums text-text-primary">
                      {formatValue(f.value, f.fact_kind)}
                    </td>
                    <td className="py-1.5 pr-3 font-mono text-text-muted">
                      {periodLabel(f)}
                    </td>
                    <td className="py-1.5 pr-3">
                      <span className="flex flex-wrap items-center gap-1">
                        <Badge label={st.label} className={st.className} />
                        {correctedFields.length > 0 && (
                          <Badge
                            label={`↻ corrected: ${correctedFields.join(", ")}`}
                            className="text-reconciled border-reconciled/40"
                          />
                        )}
                        {assumed.map((flag) => (
                          <Badge
                            key={flag}
                            label={`⚠ ${ASSUMPTION_LABELS[flag] ?? flag}`}
                            className="text-review border-review/50"
                          />
                        ))}
                        {assumed.length > 0 && (
                          <span
                            title="confidence lowered for the assumptions above"
                            className="font-mono text-meta text-text-muted"
                          >
                            {(f.extraction_confidence * 100).toFixed(0)}%
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="py-1.5 pr-4 text-meta text-text-muted">
                      <span>p{f.page_number ?? "?"}</span>
                      {f.provider_used && (
                        <span
                          className="ml-1.5 font-mono"
                          title="LLM provider that produced this fact"
                        >
                          · {f.provider_used}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function keyOf(f: Fact, key: SortKey): string {
  switch (key) {
    case "entity":
      return f.entity.toLowerCase();
    case "attribute":
      return f.attribute.toLowerCase();
    case "value":
      return String(f.value.number ?? f.value.state ?? f.value.text ?? "");
    case "period":
      return f.period.raw_label ?? "";
    case "status":
      return f.verification_status;
  }
}

function toggle(
  set: (u: (s: { key: SortKey; dir: 1 | -1 }) => { key: SortKey; dir: 1 | -1 }) => void,
  key: SortKey,
) {
  set((s) => (s.key === key ? { key, dir: (s.dir * -1) as 1 | -1 } : { key, dir: 1 }));
}

function Th({
  children,
  onClick,
  className = "",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <th
      onClick={onClick}
      className={`cursor-pointer select-none py-2 pr-3 font-medium first:pl-4 hover:text-text-primary ${className}`}
    >
      {children}
    </th>
  );
}

function FilterInput({
  placeholder,
  value,
  onChange,
}: {
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-36 rounded border border-hairline bg-raised px-2 py-1 text-cell text-text-primary placeholder:text-text-muted"
    />
  );
}

function FilterSelect({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded border border-hairline bg-raised px-2 py-1 text-cell text-text-primary"
    >
      {options.map((o) => (
        <option key={o} value={o}>
          {o || "any"}
        </option>
      ))}
    </select>
  );
}

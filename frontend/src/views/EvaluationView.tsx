import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { ErrorState, Spinner } from "@/components/common";
import type { Evaluation, TimelinePoint } from "@/api/types";

const STATUS_ORDER = [
  "verified",
  "auto_corrected",
  "needs_review",
  "rejected",
  "pending",
];
const STATUS_COLOR: Record<string, string> = {
  verified: "bg-corroborates",
  auto_corrected: "bg-reconciled",
  needs_review: "bg-review",
  rejected: "bg-contradicts",
  pending: "bg-text-muted",
};

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function StatusBar({ counts }: { counts: Record<string, number> }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  if (total === 0) return <span className="text-meta text-text-muted">—</span>;
  return (
    <div className="flex h-2 w-full overflow-hidden rounded">
      {STATUS_ORDER.filter((s) => counts[s]).map((s) => (
        <div
          key={s}
          className={STATUS_COLOR[s]}
          style={{ width: `${((counts[s] ?? 0) / total) * 100}%` }}
          title={`${s}: ${counts[s]}`}
        />
      ))}
    </div>
  );
}

/** Tiny inline sparkline for a rate over the processing timeline (0..1). */
function Sparkline({
  points,
  pick,
  color,
}: {
  points: TimelinePoint[];
  pick: (p: TimelinePoint) => number;
  color: string;
}) {
  if (points.length < 2) return null;
  const w = 160;
  const h = 34;
  const step = w / (points.length - 1);
  const d = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${i * step} ${h - pick(p) * h}`)
    .join(" ");
  return (
    <svg width={w} height={h} className="overflow-visible">
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} />
      {points.map((p, i) => (
        <circle key={i} cx={i * step} cy={h - pick(p) * h} r={2} fill={color} />
      ))}
    </svg>
  );
}

export function EvaluationView({ projectId }: { projectId: string }) {
  const ev = useQuery<Evaluation>({
    queryKey: ["evaluation", projectId],
    queryFn: () => api.getEvaluation(projectId),
    refetchInterval: 5000,
  });

  if (ev.isLoading)
    return (
      <div className="p-6">
        <Spinner />
      </div>
    );
  if (ev.error) return <ErrorState message={String(ev.error)} />;
  const d = ev.data!;

  return (
    <div className="max-w-3xl space-y-8 p-6">
      <p className="text-meta text-text-muted">
        Computed live from {d.grounding_checks} grounding check
        {d.grounding_checks === 1 ? "" : "s"} and {d.independent_verify_calls}{" "}
        independent-verification call
        {d.independent_verify_calls === 1 ? "" : "s"}. Nothing here is stored.
      </p>

      <section>
        <h3 className="text-section text-text-primary">Grounding</h3>
        <div className="mt-2 flex items-baseline justify-between border-b border-hairline py-2.5">
          <div>
            <div className="text-cell text-text-primary">Grounding pass rate</div>
            <div className="text-meta text-text-muted">
              {d.grounding_pass} of {d.grounding_checks} evidence spans were a
              verified literal substring — this sits near 100% because failures
              are dropped before storage
            </div>
          </div>
          <div className="font-mono text-title tabular-nums text-text-primary">
            {pct(d.grounding_pass_rate)}
          </div>
        </div>
      </section>

      <section>
        <h3 className="text-section text-text-primary">
          Independent verification outcome
        </h3>
        <div className="mt-2">
          <StatusBar counts={d.facts_by_status} />
        </div>
        <div className="mt-3 grid grid-cols-2 gap-x-8 gap-y-1.5 text-cell sm:grid-cols-4">
          <Stat label="Verified" value={pct(d.verified_rate)} />
          <Stat label="Auto-corrected" value={pct(d.auto_correction_rate)} />
          <Stat label="Needs review" value={pct(d.needs_review_rate)} />
          <Stat label="Rejected" value={pct(d.rejected_rate)} />
        </div>
        <div className="mt-3 text-meta text-text-muted">
          raw verifier verdicts:{" "}
          {Object.entries(d.independent_verify_breakdown)
            .map(([k, v]) => `${k} ${v}`)
            .join(" · ") || "none yet"}
        </div>
      </section>

      {d.timeline.length >= 2 && (
        <section>
          <h3 className="text-section text-text-primary">Trend across documents</h3>
          <div className="mt-2 flex flex-wrap gap-8">
            <TrendCell
              label="grounding pass rate"
              value={pct(d.timeline[d.timeline.length - 1].grounding_pass_rate)}
            >
              <Sparkline
                points={d.timeline}
                pick={(p) => p.grounding_pass_rate}
                color="#7FA285"
              />
            </TrendCell>
            <TrendCell
              label="needs-review rate"
              value={pct(d.timeline[d.timeline.length - 1].needs_review_rate)}
            >
              <Sparkline
                points={d.timeline}
                pick={(p) => p.needs_review_rate}
                color="#8C8577"
              />
            </TrendCell>
          </div>
        </section>
      )}

      {d.per_document.length > 0 && (
        <section>
          <h3 className="text-section text-text-primary">By document</h3>
          <table className="mt-2 w-full border-collapse text-cell">
            <thead>
              <tr className="border-b border-hairline text-left text-meta text-text-muted">
                <th className="py-2 pr-3 font-medium">Document</th>
                <th className="py-2 pr-3 text-right font-medium">Facts</th>
                <th className="py-2 pr-3 text-right font-medium">Grounding</th>
                <th className="py-2 pr-3 font-medium">Verification outcome</th>
              </tr>
            </thead>
            <tbody>
              {d.per_document.map((doc) => (
                <tr key={doc.document_id} className="border-b border-hairline">
                  <td className="max-w-[16rem] truncate py-2 pr-3 text-text-primary">
                    {doc.filename}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-text-muted">
                    {doc.facts_total}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-text-muted">
                    {doc.grounding_checks
                      ? pct(doc.grounding_pass_rate)
                      : "—"}
                  </td>
                  <td className="w-40 py-2 pr-3">
                    <StatusBar counts={doc.facts_by_status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-meta text-text-muted">{label}</div>
      <div className="font-mono tabular-nums text-text-primary">{value}</div>
    </div>
  );
}

function TrendCell({
  label,
  value,
  children,
}: {
  label: string;
  value: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-meta text-text-muted">{label}</div>
      <div className="font-mono text-section tabular-nums text-text-primary">
        {value}
      </div>
      <div className="mt-1">{children}</div>
    </div>
  );
}

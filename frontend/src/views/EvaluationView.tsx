import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { ErrorState, Spinner } from "@/components/common";

function StatRow({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="flex items-baseline justify-between border-b border-hairline py-2.5">
      <div>
        <div className="text-cell text-text-primary">{label}</div>
        {hint && <div className="text-meta text-text-muted">{hint}</div>}
      </div>
      <div className="font-mono text-title tabular-nums text-text-primary">{value}</div>
    </div>
  );
}

export function EvaluationView({ projectId }: { projectId: string }) {
  const ev = useQuery({
    queryKey: ["evaluation", projectId],
    queryFn: () => api.getEvaluation(projectId),
  });

  if (ev.isLoading) return <div className="p-6"><Spinner /></div>;
  if (ev.error) return <ErrorState message={String(ev.error)} />;
  const d = ev.data!;

  return (
    <div className="max-w-2xl space-y-6 p-6">
      <section>
        <h3 className="text-section text-text-primary">Grounding</h3>
        <StatRow
          label="Grounding pass rate"
          value={`${(d.grounding_pass_rate * 100).toFixed(1)}%`}
          hint={`${d.grounding_checks} checks; failures are dropped before storage, so this sits near 100%`}
        />
      </section>

      <section>
        <h3 className="text-section text-text-primary">Independent verification</h3>
        {Object.entries(d.independent_verify_breakdown).length === 0 && (
          <p className="py-2 text-meta text-text-muted">No verification runs yet.</p>
        )}
        {Object.entries(d.independent_verify_breakdown).map(([k, v]) => (
          <StatRow key={k} label={k} value={String(v)} />
        ))}
      </section>

      <section>
        <h3 className="text-section text-text-primary">Facts by status</h3>
        {Object.entries(d.facts_by_status).map(([k, v]) => (
          <StatRow key={k} label={k} value={String(v)} />
        ))}
        <StatRow
          label="Auto-correction rate"
          value={`${(d.auto_correction_rate * 100).toFixed(1)}%`}
        />
        <StatRow
          label="Needs-review rate"
          value={`${(d.needs_review_rate * 100).toFixed(1)}%`}
        />
      </section>
    </div>
  );
}

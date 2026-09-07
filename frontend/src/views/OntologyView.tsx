import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { EmptyState, ErrorState, Spinner } from "@/components/common";

export function OntologyView({ projectId }: { projectId: string }) {
  const ontology = useQuery({
    queryKey: ["ontology", projectId],
    queryFn: () => api.getOntology(projectId),
  });

  if (ontology.isLoading) return <div className="p-6"><Spinner /></div>;
  if (ontology.error) return <ErrorState message={String(ontology.error)} />;

  const groups = ontology.data?.groups ?? [];
  if (groups.length === 0)
    return (
      <EmptyState
        title="No canonical concepts yet"
        hint="When the pipeline merges two ways of naming the same entity or attribute, the merged concept and its aliases appear here, grouped by the document that introduced it."
      />
    );

  const total = groups.reduce((n, g) => n + g.concepts.length, 0);

  return (
    <div className="space-y-6 p-6">
      <p className="text-meta text-text-muted">
        {total} canonical concept{total === 1 ? "" : "s"} across{" "}
        {groups.length} document{groups.length === 1 ? "" : "s"}, in the order the
        project learned them.
      </p>
      {groups.map((g) => (
        <section key={g.document_id ?? "none"}>
          <h3 className="text-section text-text-primary">
            {g.document_filename ?? "Unattributed"}
            {g.concepts[0]?.first_seen_at && (
              <span className="ml-2 font-normal text-meta text-text-muted">
                {new Date(g.concepts[0].first_seen_at).toLocaleDateString()}
              </span>
            )}
          </h3>
          <ul className="mt-2 space-y-1.5">
            {g.concepts.map((c) => (
              <li
                key={c.concept_id}
                className="flex flex-wrap items-center gap-2 border-b border-hairline py-1.5 text-cell"
              >
                <span className="rounded border border-hairline px-1.5 py-0.5 text-meta text-text-muted">
                  {c.kind}
                </span>
                <span className="text-text-primary">{c.canonical_name}</span>
                <span className="flex flex-wrap gap-1">
                  {c.raw_aliases
                    .filter((a) => a.toLowerCase() !== c.canonical_name.toLowerCase())
                    .map((a) => (
                      <span
                        key={a}
                        className="rounded bg-raised px-1.5 py-0.5 text-meta text-text-muted"
                      >
                        {a}
                      </span>
                    ))}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

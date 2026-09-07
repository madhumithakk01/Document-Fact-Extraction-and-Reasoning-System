import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { EvidencePanel } from "@/components/EvidencePanel";
import { Sidebar } from "@/components/Sidebar";
import { EmptyState, Spinner } from "@/components/common";
import { useUi } from "@/state/ui";
import { AskView } from "@/views/AskView";
import { DocumentsView } from "@/views/DocumentsView";
import { EvaluationView } from "@/views/EvaluationView";
import { FactsView } from "@/views/FactsView";
import { OntologyView } from "@/views/OntologyView";
import { RelationshipsView } from "@/views/RelationshipsView";

export default function App() {
  const { projectId, tab } = useUi();

  return (
    <div className="flex h-full">
      <Sidebar />
      <div className="min-w-0 flex-1">
        {projectId ? (
          <ProjectWorkspace projectId={projectId} tab={tab} />
        ) : (
          <div className="flex h-full items-center justify-center">
            <EmptyState
              title="Select or create a project"
              hint="A project is an isolated workspace of related documents. Facts and relationships never cross a project boundary."
            />
          </div>
        )}
      </div>
      {projectId && <EvidencePanel projectId={projectId} />}
    </div>
  );
}

function ProjectWorkspace({ projectId, tab }: { projectId: string; tab: string }) {
  const summary = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(projectId),
    refetchInterval: 4000,
  });

  return (
    <main className="flex h-full flex-col">
      <header className="flex items-center gap-3 border-b border-hairline px-6 py-3">
        <h1 className="text-title text-text-primary">
          {summary.data?.name ?? <Spinner />}
        </h1>
        {summary.data && (
          <span className="text-meta text-text-muted">
            {summary.data.document_count} docs · {summary.data.fact_count} facts ·{" "}
            {summary.data.relationship_count} relationships
            {summary.data.sub_cluster_count > 1 &&
              ` · ${summary.data.sub_cluster_count} sub-clusters`}
          </span>
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-hidden">
        {tab === "ask" && <AskView />}
        {tab === "documents" && <DocumentsView projectId={projectId} />}
        {tab === "facts" && <FactsView projectId={projectId} />}
        {tab === "relationships" && <RelationshipsView projectId={projectId} />}
        {tab === "ontology" && <OntologyView projectId={projectId} />}
        {tab === "evaluation" && <EvaluationView projectId={projectId} />}
      </div>
    </main>
  );
}

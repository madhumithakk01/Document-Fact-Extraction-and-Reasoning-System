import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/api/client";
import { Spinner } from "@/components/common";
import { useUi, type Tab } from "@/state/ui";

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "ask", label: "Ask", icon: "◇" },
  { id: "documents", label: "Documents", icon: "▤" },
  { id: "facts", label: "Facts", icon: "≣" },
  { id: "relationships", label: "Relationships", icon: "⇄" },
  { id: "ontology", label: "Ontology", icon: "❖" },
  { id: "evaluation", label: "Evaluation", icon: "▨" },
];

export function Sidebar() {
  const { projectId, tab, setProject, setTab } = useUi();
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");

  const projects = useQuery({ queryKey: ["projects"], queryFn: api.listProjects });

  const create = useMutation({
    mutationFn: (n: string) => api.createProject(n),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      setProject(p.project_id);
      setCreating(false);
      setName("");
    },
  });

  return (
    <aside className="flex h-full w-sidebar shrink-0 flex-col border-r border-hairline bg-recessed">
      <div className="px-4 py-4">
        <span className="font-mono text-section tracking-[0.18em] text-text-primary">
          SUPERJOIN
        </span>
      </div>

      <div className="px-3">
        {creating ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) create.mutate(name.trim());
            }}
            className="flex gap-1.5"
          >
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={() => !name && setCreating(false)}
              placeholder="Project name"
              className="min-w-0 flex-1 rounded border border-hairline bg-raised px-2 py-1 text-cell text-text-primary placeholder:text-text-muted"
            />
            <button
              type="submit"
              disabled={create.isPending}
              className="rounded bg-accent px-2 py-1 text-cell text-canvas"
            >
              {create.isPending ? <Spinner /> : "Add"}
            </button>
          </form>
        ) : (
          <button
            onClick={() => setCreating(true)}
            className="w-full rounded border border-hairline px-2 py-1.5 text-left text-cell text-text-muted hover:border-accent-dim hover:text-text-primary"
          >
            + New project
          </button>
        )}
      </div>

      <div className="mt-5 px-4 text-meta text-text-muted">Projects</div>
      <nav className="mt-1 flex-1 overflow-y-auto px-2">
        {projects.isLoading && (
          <div className="px-2 py-2 text-meta text-text-muted">
            <Spinner /> loading
          </div>
        )}
        {projects.data?.length === 0 && (
          <div className="px-2 py-2 text-meta text-text-muted">
            No projects yet.
          </div>
        )}
        {projects.data?.map((p) => (
          <button
            key={p.project_id}
            onClick={() => setProject(p.project_id)}
            className={`block w-full truncate rounded px-2 py-1.5 text-left text-cell ${
              p.project_id === projectId
                ? "bg-raised text-text-primary"
                : "text-text-muted hover:text-text-primary"
            }`}
          >
            {p.name}
          </button>
        ))}
      </nav>

      {projectId && (
        <div className="border-t border-hairline py-2">
          {TABS.map((t) => {
            const active = t.id === tab;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`relative flex w-full items-center gap-2.5 px-4 py-1.5 text-cell ${
                  active
                    ? "bg-raised text-text-primary"
                    : "text-text-muted hover:text-text-primary"
                }`}
              >
                {active && (
                  <span className="absolute left-0 top-0 h-full w-0.5 bg-accent" />
                )}
                <span className="w-4 text-center text-text-muted">{t.icon}</span>
                {t.label}
              </button>
            );
          })}
        </div>
      )}
    </aside>
  );
}

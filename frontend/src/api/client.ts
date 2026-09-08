import type {
  DocumentOut,
  DocumentStatus,
  Evaluation,
  Evidence,
  Fact,
  Ontology,
  Project,
  ProjectSummary,
  QueryResult,
  Relationship,
  RelationshipDetail,
} from "./types";

export const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ??
  "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`${status}: ${detail}`);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function json(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

/** Resolve a page-image URL from the backend against the API base. */
export function mediaUrl(ref: string | null): string | null {
  if (!ref) return null;
  return ref.startsWith("http") ? ref : `${API_BASE}${ref}`;
}

export const api = {
  listProjects: () => request<Project[]>("/projects"),
  createProject: (name: string) => request<Project>("/projects", json({ name })),
  deleteProject: (pid: string) =>
    request<void>(`/projects/${pid}`, { method: "DELETE" }),
  getProject: (pid: string) => request<ProjectSummary>(`/projects/${pid}`),

  listDocuments: (pid: string) =>
    request<DocumentOut[]>(`/projects/${pid}/documents`),
  documentStatus: (pid: string, did: string) =>
    request<DocumentStatus>(`/projects/${pid}/documents/${did}/status`),
  deleteDocument: (pid: string, did: string) =>
    request<void>(`/projects/${pid}/documents/${did}`, { method: "DELETE" }),
  uploadDocument: (pid: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentOut>(`/projects/${pid}/documents`, {
      method: "POST",
      body: form,
    });
  },

  listFacts: (
    pid: string,
    params: Record<string, string | undefined> = {},
  ) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v) q.set(k, v);
    const s = q.toString();
    return request<Fact[]>(`/projects/${pid}/facts${s ? `?${s}` : ""}`);
  },
  getFact: (pid: string, fid: string) =>
    request<Fact>(`/projects/${pid}/facts/${fid}`),
  getEvidence: (pid: string, fid: string) =>
    request<Evidence>(`/projects/${pid}/facts/${fid}/evidence`),

  listRelationships: (
    pid: string,
    params: Record<string, string | undefined> = {},
  ) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v) q.set(k, v);
    const s = q.toString();
    return request<Relationship[]>(
      `/projects/${pid}/relationships${s ? `?${s}` : ""}`,
    );
  },
  getRelationship: (pid: string, rid: string) =>
    request<RelationshipDetail>(`/projects/${pid}/relationships/${rid}`),

  getOntology: (pid: string) => request<Ontology>(`/projects/${pid}/ontology`),
  getEvaluation: (pid: string) =>
    request<Evaluation>(`/projects/${pid}/evaluation`),

  query: (pid: string, question: string) =>
    request<QueryResult>(`/projects/${pid}/query`, json({ question })),
};

import { create } from "zustand";

export type Tab =
  | "ask"
  | "documents"
  | "facts"
  | "relationships"
  | "ontology"
  | "evaluation";

interface UiState {
  projectId: string | null;
  tab: Tab;
  // the fact whose evidence is shown in the docked panel; null = panel closed
  evidenceFactId: string | null;
  // ids to page through with the panel's prev/next (e.g. the current fact table)
  evidenceContext: string[];

  setProject: (id: string | null) => void;
  setTab: (t: Tab) => void;
  openEvidence: (factId: string, context?: string[]) => void;
  closeEvidence: () => void;
  stepEvidence: (dir: -1 | 1) => void;
}

const LAST_PROJECT_KEY = "factlayer.lastProject";

export const useUi = create<UiState>((set, get) => ({
  projectId:
    (typeof localStorage !== "undefined" &&
      localStorage.getItem(LAST_PROJECT_KEY)) ||
    null,
  tab: "documents",
  evidenceFactId: null,
  evidenceContext: [],

  setProject: (id) => {
    try {
      if (id) localStorage.setItem(LAST_PROJECT_KEY, id);
    } catch {
      /* ignore */
    }
    set({ projectId: id, evidenceFactId: null, tab: "documents" });
  },
  setTab: (tab) => set({ tab }),
  openEvidence: (factId, context) =>
    set((s) => ({
      evidenceFactId: factId,
      evidenceContext: context ?? s.evidenceContext,
    })),
  closeEvidence: () => set({ evidenceFactId: null }),
  stepEvidence: (dir) => {
    const { evidenceFactId, evidenceContext } = get();
    if (!evidenceFactId || evidenceContext.length === 0) return;
    const i = evidenceContext.indexOf(evidenceFactId);
    if (i === -1) return;
    const next = evidenceContext[i + dir];
    if (next) set({ evidenceFactId: next });
  },
}));

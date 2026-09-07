import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api, mediaUrl } from "@/api/client";
import { Spinner } from "@/components/common";
import type { Evidence } from "@/api/types";
import { useUi } from "@/state/ui";

export function EvidencePanel({ projectId }: { projectId: string }) {
  const { evidenceFactId, evidenceContext, closeEvidence, stepEvidence } = useUi();
  const open = evidenceFactId != null;

  const evidence = useQuery({
    queryKey: ["evidence", projectId, evidenceFactId],
    queryFn: () => api.getEvidence(projectId, evidenceFactId!),
    enabled: open,
  });

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeEvidence();
      if (e.key === "ArrowLeft") stepEvidence(-1);
      if (e.key === "ArrowRight") stepEvidence(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, closeEvidence, stepEvidence]);

  if (!open) return null;

  const idx = evidenceContext.indexOf(evidenceFactId);
  const hasContext = evidenceContext.length > 1 && idx >= 0;

  return (
    <aside
      className="animate-slide-in fixed inset-y-0 right-0 z-20 flex w-full flex-col border-l border-hairline bg-recessed shadow-2xl sm:w-evidence"
      role="dialog"
      aria-label="Evidence"
    >
      <header className="flex items-center gap-2 border-b border-hairline px-4 py-2.5">
        <div className="min-w-0 flex-1 truncate text-meta text-text-muted">
          {evidence.data
            ? `${evidence.data.filename} › page ${evidence.data.page_number ?? "?"}`
            : "loading evidence…"}
        </div>
        {hasContext && (
          <div className="flex items-center gap-1 text-text-muted">
            <button
              className="rounded px-1.5 py-0.5 hover:text-text-primary disabled:opacity-30"
              disabled={idx <= 0}
              onClick={() => stepEvidence(-1)}
              aria-label="previous evidence"
            >
              ‹
            </button>
            <span className="font-mono text-meta">
              {idx + 1}/{evidenceContext.length}
            </span>
            <button
              className="rounded px-1.5 py-0.5 hover:text-text-primary disabled:opacity-30"
              disabled={idx >= evidenceContext.length - 1}
              onClick={() => stepEvidence(1)}
              aria-label="next evidence"
            >
              ›
            </button>
          </div>
        )}
        <button
          onClick={closeEvidence}
          className="rounded px-2 py-0.5 text-text-muted hover:text-text-primary"
          aria-label="close evidence panel"
        >
          ✕
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {evidence.isLoading && <Spinner />}
        {evidence.error && (
          <p className="text-cell text-contradicts">{String(evidence.error)}</p>
        )}
        {evidence.data && <EvidenceBody data={evidence.data} />}
      </div>
    </aside>
  );
}

function EvidenceBody({ data }: { data: Evidence }) {
  const imgUrl = mediaUrl(data.page_image_url);
  const boxes = data.highlight_bboxes_normalized;

  return (
    <>
      {imgUrl && (
        <div className="relative mb-4 overflow-hidden rounded border border-hairline">
          <img src={imgUrl} alt={`page ${data.page_number}`} className="block w-full" />
          {boxes.map((b, i) => (
            <span
              key={i}
              className="animate-pulse-once pointer-events-none absolute rounded-[1px]"
              style={{
                left: `${b.x0 * 100}%`,
                top: `${b.y0 * 100}%`,
                width: `${(b.x1 - b.x0) * 100}%`,
                height: `${(b.y1 - b.y0) * 100}%`,
                backgroundColor: "rgba(201,100,66,0.22)",
                outline: "1px solid rgba(201,100,66,0.55)",
              }}
            />
          ))}
        </div>
      )}

      <p className="mb-1.5 text-meta text-text-muted">Evidence in context</p>
      <p className="whitespace-pre-wrap font-mono text-cell leading-relaxed text-text-muted">
        <HighlightedText
          text={data.surrounding_text || data.evidence_text}
          span={data.evidence_text}
        />
      </p>
    </>
  );
}

function HighlightedText({ text, span }: { text: string; span: string }) {
  const markRef = useRef<HTMLElement>(null);
  const norm = (s: string) => s.replace(/\s+/g, " ").trim();
  const nText = norm(text);
  const nSpan = norm(span);
  const at = nText.toLowerCase().indexOf(nSpan.toLowerCase());

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [text, span]);

  if (at === -1 || !nSpan) return <>{text}</>;
  return (
    <>
      {nText.slice(0, at)}
      <mark
        ref={markRef}
        className="animate-pulse-once rounded-[2px] bg-accent/25 text-text-primary"
      >
        {nText.slice(at, at + nSpan.length)}
      </mark>
      {nText.slice(at + nSpan.length)}
    </>
  );
}

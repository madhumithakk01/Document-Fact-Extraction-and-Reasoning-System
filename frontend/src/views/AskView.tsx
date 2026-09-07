import { useMutation } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { api, ApiError } from "@/api/client";
import { Spinner } from "@/components/common";
import type { QueryCitation, QueryResult } from "@/api/types";
import { useUi } from "@/state/ui";

export function AskView({ projectId }: { projectId: string }) {
  const [question, setQuestion] = useState("");
  const [showTrace, setShowTrace] = useState(false);
  const ask = useMutation({
    mutationFn: (q: string) => api.query(projectId, q),
  });
  const result = ask.data;

  return (
    <div className="mx-auto max-w-[74ch] px-6 py-8">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim()) ask.mutate(question.trim());
        }}
        className="flex gap-2"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about this project's facts…"
          className="min-w-0 flex-1 rounded border border-hairline bg-raised px-3 py-2 text-body text-text-primary placeholder:text-text-muted"
        />
        <button
          type="submit"
          disabled={ask.isPending || !question.trim()}
          className="rounded bg-accent px-4 py-2 text-cell text-canvas disabled:opacity-40"
        >
          {ask.isPending ? <Spinner /> : "Ask"}
        </button>
      </form>

      {ask.error instanceof ApiError && (
        <p className="mt-4 text-cell text-contradicts">{ask.error.detail}</p>
      )}

      {ask.isPending && (
        <p className="mt-6 text-meta text-text-muted">
          <Spinner /> gathering facts and synthesising…
        </p>
      )}

      {result && (
        <div className="mt-6">
          <p className="text-meta text-text-muted">Q</p>
          <p className="text-body text-text-primary">{result.question}</p>

          <p className="mt-4 whitespace-pre-wrap text-body leading-relaxed text-text-primary">
            <AnswerText answer={result.answer} citations={result.citations} />
          </p>

          {result.disagreements.length > 0 && (
            <div className="mt-4 space-y-2">
              {result.disagreements.map((d, i) => (
                <div
                  key={i}
                  className={`rounded border px-3 py-2 text-cell ${
                    d.relationship_type === "contradicts"
                      ? "border-contradicts/40 bg-contradicts/5 text-contradicts"
                      : "border-reconciled/40 bg-reconciled/5 text-reconciled"
                  }`}
                >
                  <span className="font-medium">
                    {d.relationship_type === "contradicts"
                      ? "Contradiction"
                      : "Reconciled"}
                    {d.reconciliation_basis && ` · ${d.reconciliation_basis}`}:
                  </span>{" "}
                  {d.explanation}
                  <span className="ml-1 text-text-muted">
                    [{d.marker_a}] vs [{d.marker_b}]
                  </span>
                </div>
              ))}
            </div>
          )}

          {result.citations.length > 0 && (
            <div className="mt-5 border-t border-hairline pt-3">
              <p className="text-meta text-text-muted">Sources</p>
              <ul className="mt-1 space-y-1">
                {result.citations.map((c) => (
                  <li key={c.marker} className="text-meta">
                    <CitationChip citation={c} />{" "}
                    <span className="text-text-muted">
                      {c.entity} / {c.attribute} = {c.value_summary}
                      {c.period ? ` · ${c.period}` : ""} · {c.document_filename}
                      {c.page_number ? ` p${c.page_number}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <button
            onClick={() => setShowTrace((s) => !s)}
            className="mt-4 text-meta text-text-muted hover:text-text-primary"
          >
            {showTrace ? "▾" : "▸"} reasoning trace ({result.tool_calls_used} tool
            call{result.tool_calls_used === 1 ? "" : "s"})
          </button>
          {showTrace && <Trace result={result} />}
        </div>
      )}
    </div>
  );
}

/** Render answer text, turning [F1]-style markers into clickable chips. */
function AnswerText({
  answer,
  citations,
}: {
  answer: string;
  citations: QueryCitation[];
}) {
  const byMarker = new Map(citations.map((c) => [c.marker, c]));
  const parts = answer.split(/(\[F\d+\])/g);
  return (
    <>
      {parts.map((part, i) => {
        const m = /^\[(F\d+)\]$/.exec(part);
        const c = m && byMarker.get(m[1]);
        if (c) return <CitationChip key={i} citation={c} />;
        return <Fragment key={i}>{part}</Fragment>;
      })}
    </>
  );
}

function CitationChip({ citation }: { citation: QueryCitation }) {
  const { openEvidence } = useUi();
  return (
    <button
      onClick={() => openEvidence(citation.fact_id, [citation.fact_id])}
      title={`${citation.document_filename}${
        citation.page_number ? ` · p${citation.page_number}` : ""
      }`}
      className="mx-0.5 inline-flex items-center rounded bg-accent-dim/60 px-1.5 py-px align-baseline font-mono text-meta text-accent hover:bg-accent-dim"
    >
      {citation.document_filename.replace(/\.pdf$/i, "")}
      {citation.page_number ? ` · p${citation.page_number}` : ""}
    </button>
  );
}

function Trace({ result }: { result: QueryResult }) {
  return (
    <ol className="mt-2 list-decimal space-y-2 rounded border border-hairline bg-recessed p-3 pl-7 text-meta text-text-muted">
      {result.trace.map((t, i) => (
        <li key={i}>
          <span className="text-text-primary">{t.tool}</span>
          {t.args && Object.keys(t.args).length > 0 && (
            <span> {JSON.stringify(t.args)}</span>
          )}
          {t.rationale && <span> — {t.rationale}</span>}
          {t.result && (
            <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-[11px] text-text-muted">
              {t.result}
            </pre>
          )}
        </li>
      ))}
    </ol>
  );
}

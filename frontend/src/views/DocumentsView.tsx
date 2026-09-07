import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { api, ApiError } from "@/api/client";
import { Badge } from "@/components/Badge";
import { EmptyState, ErrorState, Spinner } from "@/components/common";
import type { DocumentOut, ProcessingStatus } from "@/api/types";

const STATUS_STAGES: ProcessingStatus[] = [
  "queued",
  "extracting",
  "verifying",
  "comparing",
  "ready",
];

function statusMeta(s: ProcessingStatus) {
  if (s === "ready") return { label: "Ready", cls: "text-corroborates border-corroborates/40" };
  if (s === "failed") return { label: "Failed", cls: "text-contradicts border-contradicts/40" };
  const i = STATUS_STAGES.indexOf(s);
  return {
    label: `${s}  ${i >= 0 ? i + 1 : "?"}/4`,
    cls: "text-reconciled border-reconciled/40",
  };
}

export function DocumentsView({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const docs = useQuery({
    queryKey: ["documents", projectId],
    queryFn: () => api.listDocuments(projectId),
    refetchInterval: (q) =>
      (q.state.data ?? []).some(
        (d: DocumentOut) => d.processing_status !== "ready" && d.processing_status !== "failed",
      )
        ? 2000
        : false,
  });

  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const upload = useMutation({
    mutationFn: (file: File) => api.uploadDocument(projectId, file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents", projectId] }),
  });

  const onFiles = useCallback(
    (files: FileList | null) => {
      const file = files?.[0];
      if (file) upload.mutate(file);
    },
    [upload],
  );

  const del = useMutation({
    mutationFn: (did: string) => api.deleteDocument(projectId, did),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents", projectId] });
      qc.invalidateQueries({ queryKey: ["facts", projectId] });
    },
  });

  return (
    <div className="p-6">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          onFiles(e.dataTransfer.files);
        }}
        className={`mb-6 flex flex-col items-center justify-center rounded border border-dashed px-6 py-8 text-center ${
          dragging ? "border-accent bg-accent/5" : "border-hairline"
        }`}
      >
        <p className="text-cell text-text-muted">
          Drop a PDF here, or{" "}
          <button
            className="text-accent underline-offset-2 hover:underline"
            onClick={() => inputRef.current?.click()}
          >
            browse
          </button>
        </p>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          hidden
          onChange={(e) => onFiles(e.target.files)}
        />
        {upload.isPending && (
          <p className="mt-2 text-meta text-text-muted">
            <Spinner /> uploading…
          </p>
        )}
        {upload.error instanceof ApiError && (
          <p className="mt-2 text-meta text-contradicts">{upload.error.detail}</p>
        )}
      </div>

      {docs.isLoading && <Spinner />}
      {docs.error && <ErrorState message={String(docs.error)} />}
      {docs.data?.length === 0 && (
        <EmptyState
          title="No documents yet"
          hint="Upload a PDF to begin. It runs through ingestion, extraction, verification, and comparison automatically."
        />
      )}

      {docs.data && docs.data.length > 0 && (
        <table className="w-full border-collapse text-cell">
          <thead>
            <tr className="border-b border-hairline text-left text-meta text-text-muted">
              <th className="py-2 pr-3 font-medium">Filename</th>
              <th className="py-2 pr-3 font-medium">Type</th>
              <th className="py-2 pr-3 font-medium">Pages</th>
              <th className="py-2 pr-3 font-medium">Status</th>
              <th className="py-2 pr-3 text-right font-medium">Facts</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody>
            {docs.data.map((d) => (
              <DocRow
                key={d.document_id}
                doc={d}
                projectId={projectId}
                onDelete={() => del.mutate(d.document_id)}
              />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function DocRow({
  doc,
  projectId,
  onDelete,
}: {
  doc: DocumentOut;
  projectId: string;
  onDelete: () => void;
}) {
  const active = doc.processing_status !== "ready" && doc.processing_status !== "failed";
  const status = useQuery({
    queryKey: ["docStatus", doc.document_id],
    queryFn: () => api.documentStatus(projectId, doc.document_id),
    refetchInterval: active ? 2000 : false,
    enabled: true,
  });
  const meta = statusMeta(doc.processing_status);

  return (
    <tr className="group border-b border-hairline hover:bg-raised">
      <td className="max-w-[22rem] py-2 pr-3">
        <span className="block truncate text-text-primary">{doc.filename}</span>
        {doc.off_domain && (
          <span
            className="mt-0.5 inline-flex items-center gap-1 rounded border border-reconciled/40 px-1.5 py-0.5 text-meta text-reconciled"
            title={`Placed in a separate sub-cluster (${doc.sub_cluster_id}) — this document looks topically different from the others in this project.`}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-reconciled" />
            topically different
          </span>
        )}
      </td>
      <td className="py-2 pr-3 text-text-muted">{doc.content_type_detected}</td>
      <td className="py-2 pr-3 font-mono text-text-muted">{doc.page_count || "—"}</td>
      <td className="py-2 pr-3">
        <Badge label={meta.label} className={meta.cls} />
        {doc.processing_status === "failed" && doc.processing_error && (
          <div className="mt-1 max-w-[24rem] truncate text-meta text-contradicts">
            {doc.processing_error}
          </div>
        )}
      </td>
      <td className="py-2 pr-3 text-right font-mono text-text-primary">
        {status.data?.fact_count ?? "—"}
      </td>
      <td className="py-2 text-right">
        <button
          onClick={onDelete}
          className="text-meta text-text-muted opacity-0 transition-opacity hover:text-contradicts group-hover:opacity-100"
        >
          remove
        </button>
      </td>
    </tr>
  );
}

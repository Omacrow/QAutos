"use client";

import Link from "next/link";
import { type DragEvent, useId, useState } from "react";

import { ErrorState, formatRelative, PageHeader, Panel } from "@/components/app/panels";
import { Badge } from "@/components/ui/badge";
import { Spinner, StatusBadge } from "@/components/app/document-status";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, type DocumentInfo, hasRole } from "@/lib/api/client";
import {
  useDeleteDocument,
  useDocuments,
  useDownloadDocument,
  useMe,
  useUploadDocument,
} from "@/lib/api/hooks";
import { cn } from "@/lib/cn";
import {
  ACCEPTED_EXTENSIONS,
  errorMessage,
  formatBytes,
  isPending,
  MAX_UPLOAD_BYTES,
  precheckFile,
} from "@/lib/documents";

export function DocumentsView() {
  const me = useMe();
  const documents = useDocuments();
  const canEdit = hasRole(me.data?.role, "editor");

  const docs = documents.data ?? [];
  const ready = docs.filter((d) => d.status === "ready");
  const chunks = ready.reduce((sum, d) => sum + d.chunk_count, 0);

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Documents"
        description="The evidence answers are drafted from: policies, SOC 2 reports, past questionnaires. Only your organization can search them."
      />

      <div className="mb-6 grid gap-px border border-border bg-border sm:grid-cols-3">
        <Stat label="Documents" value={documents.isPending ? null : docs.length} />
        <Stat label="Indexed" value={documents.isPending ? null : ready.length} />
        <Stat label="Searchable passages" value={documents.isPending ? null : chunks} />
      </div>

      {canEdit && <Uploader />}

      {documents.error ? (
        <ErrorState error={documents.error} />
      ) : (
        <Panel
          title="Library"
          meta={docs.some(isPending) ? "Processing… updates automatically" : undefined}
        >
          <DocumentTable docs={documents.data} loading={documents.isPending} canEdit={canEdit} />
        </Panel>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="bg-surface-solid px-5 py-4">
      <p className="font-mono text-[10px] tracking-widest text-subtle-foreground uppercase">
        {label}
      </p>
      {value === null ? (
        <Skeleton className="mt-2 h-7 w-12" />
      ) : (
        <p className="mt-1 text-2xl font-semibold tabular-nums">{value.toLocaleString()}</p>
      )}
    </div>
  );
}

// --- Upload ------------------------------------------------------------------------

type UploadItem = {
  key: string;
  name: string;
  state: "waiting" | "uploading" | "done" | "duplicate" | "error";
  message?: string;
};

function Uploader() {
  const inputId = useId();
  const upload = useUploadDocument();
  const [items, setItems] = useState<UploadItem[]>([]);
  const [dragging, setDragging] = useState(false);

  const update = (key: string, patch: Partial<UploadItem>) =>
    setItems((current) => current.map((i) => (i.key === key ? { ...i, ...patch } : i)));

  async function handleFiles(files: FileList | File[]) {
    const batch = Array.from(files).map((file) => {
      const problem = precheckFile(file);
      const item: UploadItem = {
        key: `${file.name}-${file.size}-${crypto.randomUUID()}`,
        name: file.name,
        state: problem ? "error" : "waiting",
        message: problem ?? undefined,
      };
      return { file, item, problem };
    });
    setItems((current) => [...batch.map((b) => b.item), ...current].slice(0, 20));

    // One at a time: keeps the API and the embedding provider within rate limits.
    for (const { file, item, problem } of batch) {
      if (problem) continue;
      update(item.key, { state: "uploading" });
      try {
        const result = await upload.mutateAsync(file);
        update(item.key, result.duplicate ? { state: "duplicate" } : { state: "done" });
      } catch (error) {
        update(item.key, {
          state: "error",
          message: error instanceof ApiError ? error.message : "Upload failed.",
        });
      }
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length) void handleFiles(event.dataTransfer.files);
  }

  return (
    <div className="mb-6 border border-border bg-surface-solid">
      <label
        htmlFor={inputId}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "grid-backdrop flex cursor-pointer flex-col items-center gap-3 px-6 py-10 text-center transition-colors",
          dragging
            ? "bg-primary/10 outline-2 -outline-offset-8 outline-primary outline-dashed"
            : "hover:bg-muted/40",
        )}
      >
        <span className="flex size-11 items-center justify-center border border-border bg-surface-raised text-primary">
          <svg viewBox="0 0 24 24" className="size-5" aria-hidden>
            <path
              d="M12 16V4m0 0-4 4m4-4 4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <span>
          <span className="font-medium">Drop files here</span>{" "}
          <span className="text-muted-foreground">or</span>{" "}
          <span className="font-medium text-primary underline-offset-4 hover:underline">browse</span>
        </span>
        <span className="font-mono text-xs text-subtle-foreground">
          PDF · DOCX · XLSX — up to {formatBytes(MAX_UPLOAD_BYTES)} each
        </span>
        <input
          id={inputId}
          type="file"
          multiple
          accept={ACCEPTED_EXTENSIONS.join(",")}
          className="sr-only"
          onChange={(e) => {
            if (e.target.files?.length) void handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </label>
      {items.length > 0 && (
        <ul className="border-t border-border">
          {items.map((item) => (
            <li
              key={item.key}
              className="flex items-center justify-between gap-4 border-b border-border px-5 py-2.5 text-sm last:border-b-0"
            >
              <span className="min-w-0 truncate">{item.name}</span>
              <UploadState item={item} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function UploadState({ item }: { item: UploadItem }) {
  switch (item.state) {
    case "waiting":
      return <Badge>Waiting</Badge>;
    case "uploading":
      return (
        <Badge tone="review">
          <Spinner /> Uploading
        </Badge>
      );
    case "done":
      return <Badge tone="approved">Uploaded</Badge>;
    case "duplicate":
      return <Badge tone="library">Already in library</Badge>;
    case "error":
      return (
        <span className="text-right text-xs text-manual">{item.message ?? "Upload failed."}</span>
      );
  }
}

// --- Table ---------------------------------------------------------------------------

const KIND_LABEL = { pdf: "PDF", docx: "DOCX", xlsx: "XLSX" } as const;

function DocumentTable({
  docs,
  loading,
  canEdit,
}: {
  docs?: DocumentInfo[];
  loading: boolean;
  canEdit: boolean;
}) {
  if (loading) return <Skeleton className="m-5 h-40" />;
  if (!docs?.length) {
    return (
      <p className="px-5 py-10 text-center text-sm text-muted-foreground">
        No documents yet.{canEdit ? " Upload your security policies to get started." : ""}
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-subtle-foreground">
            <th className="px-5 py-2.5 font-medium">Document</th>
            <th className="px-5 py-2.5 font-medium">Status</th>
            <th className="hidden px-5 py-2.5 text-right font-medium md:table-cell">Pages</th>
            <th className="hidden px-5 py-2.5 text-right font-medium md:table-cell">Passages</th>
            <th className="hidden px-5 py-2.5 text-right font-medium lg:table-cell">Size</th>
            <th className="hidden px-5 py-2.5 font-medium lg:table-cell">Added</th>
            <th className="px-5 py-2.5">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {docs.map((doc) => (
            <DocumentRow key={doc.id} doc={doc} canEdit={canEdit} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DocumentRow({ doc, canEdit }: { doc: DocumentInfo; canEdit: boolean }) {
  const remove = useDeleteDocument();
  const download = useDownloadDocument();
  return (
    <tr className="border-b border-border align-top last:border-b-0 hover:bg-muted/30">
      <td className="max-w-0 px-5 py-3 sm:w-[40%]">
        <div className="flex items-center gap-3">
          <span className="flex h-8 w-11 shrink-0 items-center justify-center border border-border bg-surface-raised font-mono text-[10px] text-primary">
            {KIND_LABEL[doc.kind]}
          </span>
          <Link
            href={`/documents/${doc.id}`}
            className="min-w-0 truncate font-medium underline-offset-4 hover:text-primary hover:underline"
          >
            {doc.filename}
          </Link>
        </div>
      </td>
      <td className="px-5 py-3">
        <StatusBadge doc={doc} />
        {doc.status === "failed" && (
          <p className="mt-1 max-w-56 text-xs text-muted-foreground">
            {errorMessage(doc.error_code)}
          </p>
        )}
      </td>
      <td className="hidden px-5 py-3 text-right tabular-nums text-muted-foreground md:table-cell">
        {doc.page_count ?? "—"}
      </td>
      <td className="hidden px-5 py-3 text-right tabular-nums text-muted-foreground md:table-cell">
        {doc.status === "ready" ? doc.chunk_count : "—"}
      </td>
      <td className="hidden px-5 py-3 text-right tabular-nums text-muted-foreground lg:table-cell">
        {formatBytes(doc.size_bytes)}
      </td>
      <td className="hidden px-5 py-3 text-muted-foreground lg:table-cell">
        {formatRelative(doc.created_at)}
      </td>
      <td className="px-5 py-2.5">
        <div className="flex justify-end gap-1">
          <Button
            variant="ghost"
            size="sm"
            disabled={download.isPending}
            onClick={() => download.mutate({ id: doc.id })}
          >
            Download
          </Button>
          {canEdit && (
            <Button
              variant="ghost"
              size="sm"
              className="hover:text-manual"
              disabled={remove.isPending}
              onClick={() => {
                if (window.confirm(`Delete "${doc.filename}" and everything indexed from it?`)) {
                  remove.mutate(doc.id);
                }
              }}
            >
              Delete
            </Button>
          )}
        </div>
        {(remove.error ?? download.error) && (
          <p className="mt-1 text-right text-xs text-manual">
            {(remove.error ?? download.error)?.message}
          </p>
        )}
      </td>
    </tr>
  );
}

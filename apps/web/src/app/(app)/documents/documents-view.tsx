"use client";

import Link from "next/link";

import { ErrorState, formatRelative, PageHeader, Panel } from "@/components/app/panels";
import { StatusBadge } from "@/components/app/document-status";
import { Uploader } from "@/components/app/uploader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { type DocumentInfo, hasRole } from "@/lib/api/client";
import {
  useDeleteDocument,
  useDocuments,
  useDownloadDocument,
  useMe,
  useUploadDocument,
} from "@/lib/api/hooks";
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
  const upload = useUploadDocument();

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

      {canEdit && (
        <Uploader
          accept={ACCEPTED_EXTENSIONS}
          hint={`PDF · DOCX · XLSX — up to ${formatBytes(MAX_UPLOAD_BYTES)} each`}
          precheck={precheckFile}
          upload={(file) => upload.mutateAsync(file)}
          duplicateLabel="Already in library"
        />
      )}

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

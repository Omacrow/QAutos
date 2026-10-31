"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { use, useEffect, useRef, useState } from "react";

import { CitationChip } from "@/components/answer/citation-chip";
import { StatusBadge } from "@/components/app/document-status";
import { ErrorState, formatRelative, PageHeader, Panel } from "@/components/app/panels";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { type Chunk, type DocumentInfo, hasRole } from "@/lib/api/client";
import {
  useChunks,
  useDeleteDocument,
  useDocument,
  useDownloadDocument,
  useMe,
  useReprocessDocument,
} from "@/lib/api/hooks";
import { errorMessage, formatBytes, isPending } from "@/lib/documents";

const PAGE_SIZE = 20;

export function DocumentDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const document = useDocument(id);
  const me = useMe();
  const canEdit = hasRole(me.data?.role, "editor");

  if (document.error) return <ErrorState error={document.error} />;
  const doc = document.data;
  return (
    <div className="mx-auto max-w-5xl">
      <Link
        href="/documents"
        className="mb-4 inline-flex font-mono text-xs text-subtle-foreground hover:text-foreground"
      >
        ← Documents
      </Link>
      <PageHeader
        title={
          doc ? <span className="break-all">{doc.filename}</span> : <Skeleton className="h-9 w-80" />
        }
        description={doc ? <StatusBadge doc={doc} /> : undefined}
        action={doc && <Actions doc={doc} canEdit={canEdit} />}
      />
      {doc && <Facts doc={doc} />}
      {doc?.status === "failed" && (
        <div className="mb-6 border border-dashed border-manual/40 bg-manual-bg p-5 text-sm">
          <p className="font-medium text-manual">Processing failed</p>
          <p className="mt-1 text-muted-foreground">{errorMessage(doc.error_code)}</p>
        </div>
      )}
      {doc && isPending(doc) && (
        <div className="mb-6 border border-border bg-surface-solid p-5 text-sm text-muted-foreground">
          Extracting text, splitting it into passages and indexing them. This page updates
          automatically.
        </div>
      )}
      {doc?.status === "ready" && <Passages doc={doc} />}
    </div>
  );
}

function Actions({ doc, canEdit }: { doc: DocumentInfo; canEdit: boolean }) {
  const router = useRouter();
  const download = useDownloadDocument();
  const reprocess = useReprocessDocument();
  const remove = useDeleteDocument();
  const error = download.error ?? reprocess.error ?? remove.error;
  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="secondary" size="sm" onClick={() => download.mutate({ id: doc.id })}>
          Download original
        </Button>
        {doc.has_rendition && (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => download.mutate({ id: doc.id, rendition: true })}
          >
            PDF rendition
          </Button>
        )}
        {canEdit && (
          <Button
            variant="ghost"
            size="sm"
            disabled={reprocess.isPending || isPending(doc)}
            onClick={() => reprocess.mutate(doc.id)}
          >
            Reprocess
          </Button>
        )}
        {canEdit && (
          <Button
            variant="ghost"
            size="sm"
            className="hover:text-manual"
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(`Delete "${doc.filename}" and everything indexed from it?`)) {
                remove.mutate(doc.id, { onSuccess: () => router.push("/documents") });
              }
            }}
          >
            Delete
          </Button>
        )}
      </div>
      {error && <p className="text-xs text-manual">{error.message}</p>}
    </div>
  );
}

const PARSER_LABEL: Record<string, string> = {
  pymupdf: "PDF text layer",
  "libreoffice+pymupdf": "DOCX → PDF (exact pages)",
  "python-docx": "DOCX structure (pages from Word)",
  openpyxl: "Spreadsheet rows",
};

function Facts({ doc }: { doc: DocumentInfo }) {
  const facts: [string, string][] = [
    ["Type", doc.kind.toUpperCase()],
    ["Size", formatBytes(doc.size_bytes)],
    ["Pages", doc.page_count?.toString() ?? "—"],
    ["Passages", doc.status === "ready" ? doc.chunk_count.toString() : "—"],
    ["Extracted with", doc.parser ? (PARSER_LABEL[doc.parser] ?? doc.parser) : "—"],
    ["Added", `${formatRelative(doc.created_at)} by ${doc.uploaded_by ?? "system"}`],
  ];
  return (
    <dl className="mb-6 grid grid-cols-2 gap-px border border-border bg-border md:grid-cols-3">
      {facts.map(([label, value]) => (
        <div key={label} className="bg-surface-solid px-5 py-3.5">
          <dt className="font-mono text-[10px] tracking-widest text-subtle-foreground uppercase">
            {label}
          </dt>
          <dd className="mt-1 truncate text-sm">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Passages({ doc }: { doc: DocumentInfo }) {
  // ?chunk=N (from a search result) opens the page of passages containing N.
  const target = Number(useSearchParams().get("chunk") ?? NaN);
  const focused = Number.isInteger(target) && target >= 0 ? target : null;
  const [offset, setOffset] = useState(
    focused === null ? 0 : Math.floor(focused / PAGE_SIZE) * PAGE_SIZE,
  );
  const chunks = useChunks(doc.id, offset, PAGE_SIZE, true);
  const total = chunks.data?.total ?? doc.chunk_count;
  const end = Math.min(offset + PAGE_SIZE, total);
  return (
    <Panel title="Indexed passages" meta={total ? `${offset + 1}–${end} of ${total}` : undefined}>
      <p className="border-b border-border px-5 py-3 text-xs text-muted-foreground">
        These are the units retrieval searches and cites. Each keeps its section heading and the
        pages (or rows) it came from.
      </p>
      {chunks.error ? (
        <div className="p-5">
          <ErrorState error={chunks.error} />
        </div>
      ) : chunks.isPending ? (
        <Skeleton className="m-5 h-48" />
      ) : (
        <ol>
          {chunks.data?.items.map((chunk) => (
            <Passage
              key={chunk.id}
              chunk={chunk}
              documentName={doc.filename}
              focused={chunk.ordinal === focused}
            />
          ))}
        </ol>
      )}
      {total > PAGE_SIZE && (
        <div className="flex justify-between border-t border-border px-5 py-3">
          <Button
            variant="ghost"
            size="sm"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            ← Previous
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={end >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next →
          </Button>
        </div>
      )}
    </Panel>
  );
}

function Passage({
  chunk,
  documentName,
  focused,
}: {
  chunk: Chunk;
  documentName: string;
  focused: boolean;
}) {
  const ref = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (focused) ref.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [focused]);
  return (
    <li
      ref={ref}
      id={`passage-${chunk.ordinal}`}
      className={`grid scroll-mt-24 gap-2 border-b border-border px-5 py-4 last:border-b-0 sm:grid-cols-[3rem_1fr] ${
        focused ? "bg-primary/10 shadow-[inset_2px_0_0_var(--primary)]" : ""
      }`}
    >
      <span className="font-mono text-xs text-subtle-foreground">#{chunk.ordinal + 1}</span>
      <div className="min-w-0">
        <CitationChip
          documentName={documentName}
          page={chunk.page_start}
          pageEnd={chunk.page_end}
          heading={chunk.heading}
          sheet={chunk.sheet}
          rowStart={chunk.row_start}
          rowEnd={chunk.row_end}
        />
        <p className="mt-2 text-sm leading-relaxed whitespace-pre-line text-muted-foreground">
          {chunk.text}
        </p>
      </div>
    </li>
  );
}

"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";

import { CitationChip } from "@/components/answer/citation-chip";
import { ErrorState, PageHeader } from "@/components/app/panels";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { SearchHit } from "@/lib/api/client";
import { useDocuments, useOpenAtPage, useSearch } from "@/lib/api/hooks";
import { highlight, queryTerms, viewablePage } from "@/lib/search";

const EXAMPLES = [
  "Is multi-factor authentication required for staff?",
  "How long are security logs retained?",
  "What is your recovery time objective?",
  "Do you have a SOC 2 Type II report?",
];

export function SearchView() {
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const search = useSearch(query);
  const documents = useDocuments();
  const indexed = documents.data?.filter((d) => d.status === "ready").length;

  function submit(event: FormEvent) {
    event.preventDefault();
    setQuery(draft.trim());
  }

  function run(question: string) {
    setDraft(question);
    setQuery(question);
  }

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Search"
        description="Ask a questionnaire question and see the passages an answer would be drafted from, with their sources."
      />

      <form onSubmit={submit} className="border border-border bg-surface-solid">
        <div className="flex flex-col gap-3 p-4 sm:flex-row">
          <label htmlFor="search-query" className="sr-only">
            Question
          </label>
          <input
            id="search-query"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="e.g. Do you encrypt customer data at rest?"
            maxLength={1000}
            autoComplete="off"
            className="h-11 min-w-0 flex-1 rounded-md border border-border bg-background px-4 text-sm outline-none placeholder:text-subtle-foreground focus:border-primary"
          />
          <Button type="submit" size="md" disabled={draft.trim().length < 2}>
            Search
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-border px-4 py-3">
          <span className="font-mono text-[10px] tracking-widest text-subtle-foreground uppercase">
            Try
          </span>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => run(example)}
              className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
            >
              {example}
            </button>
          ))}
        </div>
      </form>

      <div className="mt-6">
        {!query ? (
          <Intro indexed={indexed} />
        ) : search.error ? (
          <ErrorState error={search.error} />
        ) : search.isPending ? (
          <div className="grid gap-px border border-border bg-border">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-36 rounded-none" />
            ))}
          </div>
        ) : (
          <Results query={query} hits={search.data.results} meta={search.data} />
        )}
      </div>
    </div>
  );
}

function Intro({ indexed }: { indexed: number | undefined }) {
  if (indexed === 0) {
    return (
      <p className="border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
        Nothing to search yet.{" "}
        <Link href="/documents" className="text-primary underline-offset-4 hover:underline">
          Upload your security documents
        </Link>{" "}
        first.
      </p>
    );
  }
  return (
    <div className="grid gap-px border border-border bg-border sm:grid-cols-3">
      {[
        ["Meaning and keywords", "Finds passages that mean the same thing, and exact terms like “TLS 1.2” or control ids."],
        ["Only your documents", "Search never leaves your organization’s indexed evidence."],
        ["Every result is cited", "Document, page or row, and section, one click from the source."],
      ].map(([title, body]) => (
        <div key={title} className="bg-surface-solid p-5">
          <p className="text-sm font-semibold">{title}</p>
          <p className="mt-1 text-xs text-muted-foreground">{body}</p>
        </div>
      ))}
    </div>
  );
}

function Results({
  query,
  hits,
  meta,
}: {
  query: string;
  hits: SearchHit[];
  meta: { mode: string; reranked: boolean; took_ms: number };
}) {
  const terms = queryTerms(query);
  return (
    <section className="border border-border bg-surface-solid">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3 text-xs text-muted-foreground">
        <span>
          {hits.length} passage{hits.length === 1 ? "" : "s"} · {meta.took_ms} ms
        </span>
        <span className="flex gap-2">
          {meta.mode === "keyword_only" ? (
            <Badge tone="review">Keyword only: semantic search unavailable</Badge>
          ) : (
            <Badge>Semantic + keyword</Badge>
          )}
          {meta.reranked && <Badge tone="library">Reranked</Badge>}
        </span>
      </div>
      {hits.length === 0 ? (
        <p className="px-5 py-10 text-center text-sm text-muted-foreground">
          No matching passages. In Phase 2, a question like this goes to a person instead of
          getting an AI answer.
        </p>
      ) : (
        <ol>
          {hits.map((hit, index) => (
            <Result key={hit.chunk_id} hit={hit} rank={index + 1} terms={terms} />
          ))}
        </ol>
      )}
    </section>
  );
}

function Result({ hit, rank, terms }: { hit: SearchHit; rank: number; terms: string[] }) {
  const open = useOpenAtPage();
  const view = viewablePage(hit);
  return (
    <li className="grid gap-3 border-b border-border px-5 py-5 last:border-b-0 sm:grid-cols-[2.5rem_1fr_9rem]">
      <span className="font-mono text-sm text-primary">{String(rank).padStart(2, "0")}</span>
      <div className="min-w-0">
        <CitationChip
          documentName={hit.document_filename}
          page={hit.page_start}
          pageEnd={hit.page_end}
          heading={hit.heading}
          sheet={hit.sheet}
          rowStart={hit.row_start}
          rowEnd={hit.row_end}
        />
        <p className="mt-3 text-sm leading-relaxed whitespace-pre-line text-muted-foreground">
          {highlight(hit.text, terms).map((segment, i) =>
            segment.match ? (
              <mark key={i} className="rounded-sm bg-primary/20 px-0.5 text-foreground">
                {segment.text}
              </mark>
            ) : (
              <span key={i}>{segment.text}</span>
            ),
          )}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {view && (
            <Button
              variant="secondary"
              size="sm"
              disabled={open.isPending}
              onClick={() => open.mutate({ id: hit.document_id, ...view })}
            >
              Open {view.page ? `page ${view.page}` : "PDF"}
            </Button>
          )}
          <Link
            href={`/documents/${hit.document_id}?chunk=${hit.ordinal}`}
            className="inline-flex h-8 items-center rounded-md px-3 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            View in document
          </Link>
        </div>
        {open.error && <p className="mt-2 text-xs text-manual">{open.error.message}</p>}
      </div>
      <Signals hit={hit} />
    </li>
  );
}

/** Why this passage ranked here. Raw signals; the calibrated confidence score comes in Phase 2. */
function Signals({ hit }: { hit: SearchHit }) {
  const rows: [string, string][] = [];
  if (hit.rerank_score != null) rows.push(["Relevance", `${Math.round(hit.rerank_score * 100)}%`]);
  rows.push([
    "Similarity",
    hit.vector_similarity != null ? hit.vector_similarity.toFixed(2) : "—",
  ]);
  rows.push(["Keyword", hit.keyword_rank != null ? `#${hit.keyword_rank}` : "no match"]);
  return (
    <dl className="grid content-start gap-1.5 text-xs sm:border-l sm:border-border sm:pl-4">
      {rows.map(([label, value]) => (
        <div key={label} className="flex justify-between gap-2">
          <dt className="text-subtle-foreground">{label}</dt>
          <dd className="font-mono text-muted-foreground">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

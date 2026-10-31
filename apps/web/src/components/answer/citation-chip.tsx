export type Citation = {
  documentName: string;
  page: number | null;
  pageEnd?: number | null;
  heading?: string | null;
  sheet?: string | null;
  rowStart?: number | null;
  rowEnd?: number | null;
};

/** "Policy · p.4–5 · §Access Control" or "Answers.xlsx · CAIQ · rows 2–4". */
export function formatCitation(c: Citation): string {
  const location =
    c.sheet != null
      ? [c.sheet, c.rowStart != null ? rowLabel(c.rowStart, c.rowEnd) : null]
      : [c.page != null ? `p.${range(c.page, c.pageEnd)}` : null];
  const heading = c.heading && c.heading !== c.sheet ? `§${c.heading}` : null;
  return [c.documentName, ...location, heading].filter(Boolean).join(" · ");
}

function rowLabel(start: number, end?: number | null): string {
  return `${end != null && end !== start ? "rows" : "row"} ${range(start, end)}`;
}

function range(start: number, end?: number | null): string {
  return end != null && end !== start ? `${start}–${end}` : String(start);
}

export function CitationChip(citation: Citation) {
  return (
    <span className="inline-flex max-w-full items-center gap-1.5 truncate rounded-sm border border-border bg-muted px-2 py-0.5 font-mono text-xs text-muted-foreground">
      <svg viewBox="0 0 16 16" className="size-3 shrink-0" aria-hidden>
        <path d="M4 1h6l3 3v11H4z" fill="none" stroke="currentColor" strokeWidth="1.3" />
      </svg>
      {formatCitation(citation)}
    </span>
  );
}

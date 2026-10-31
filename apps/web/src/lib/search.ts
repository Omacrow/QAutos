const STOP_WORDS = new Set(
  "a an and are as at be by can do does for from has have how in is it its of on or our the their this to was we what when where which who why will with you your".split(
    " ",
  ),
);

/** Words worth highlighting in results: 3+ characters, not stop words. */
export function queryTerms(query: string): string[] {
  const words = query.toLowerCase().match(/[\p{L}\p{N}][\p{L}\p{N}.-]*[\p{L}\p{N}]|[\p{L}\p{N}]/gu);
  return [...new Set((words ?? []).filter((w) => w.length >= 3 && !STOP_WORDS.has(w)))];
}

export type Segment = { text: string; match: boolean };

/** Split text into matched / unmatched segments. Matches word prefixes ("encrypt" ⊂ "encrypted"). */
export function highlight(text: string, terms: string[]): Segment[] {
  if (!terms.length) return [{ text, match: false }];
  const escaped = terms
    .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .sort((a, b) => b.length - a.length);
  const pattern = new RegExp(`(?<![\\p{L}\\p{N}])(?:${escaped.join("|")})`, "giu");
  const segments: Segment[] = [];
  let last = 0;
  for (const m of text.matchAll(pattern)) {
    const start = m.index;
    if (start > last) segments.push({ text: text.slice(last, start), match: false });
    segments.push({ text: m[0], match: true });
    last = start + m[0].length;
  }
  if (last < text.length) segments.push({ text: text.slice(last), match: false });
  return segments;
}

/** Page to open for a hit, or null when the source can't be opened as a PDF. */
export function viewablePage(hit: {
  document_kind: string;
  document_has_rendition: boolean;
  page_start: number | null;
}): { rendition: boolean; page: number | null } | null {
  if (hit.document_kind === "pdf") return { rendition: false, page: hit.page_start };
  if (hit.document_kind === "docx" && hit.document_has_rendition) {
    return { rendition: true, page: hit.page_start };
  }
  return null;
}

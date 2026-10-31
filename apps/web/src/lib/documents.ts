import type { Tone } from "@/components/ui/badge";
import type { DocumentInfo, DocumentStatus } from "@/lib/api/client";

/** Mirrors the API limit (MAX_UPLOAD_BYTES), which is what actually enforces it. */
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
export const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".xlsx"] as const;

const ERROR_MESSAGES: Record<string, string> = {
  no_text: "No selectable text found. Scanned documents need OCR, which isn't supported yet.",
  encrypted: "The PDF is password-protected. Upload an unlocked copy.",
  too_many_pages: "The document has more pages than the limit.",
  too_large: "The file is too large to process.",
  corrupt: "The file appears to be damaged.",
  conversion_failed: "This DOCX couldn't be converted to PDF.",
  embedding_failed: "Indexing failed. Try reprocessing.",
  queue_unavailable: "Processing couldn't start. Try reprocessing.",
  internal: "Something went wrong while processing. Try reprocessing.",
};

export function errorMessage(code: string | null | undefined): string {
  return (code && ERROR_MESSAGES[code]) || "Processing failed.";
}

export const STATUS_TONE: Record<DocumentStatus, Tone> = {
  queued: "review",
  processing: "review",
  ready: "approved",
  failed: "manual",
};

export function isPending(doc: Pick<DocumentInfo, "status">): boolean {
  return doc.status === "queued" || doc.status === "processing";
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

/** Client-side pre-check so obvious mistakes fail instantly. The API re-checks everything. */
export function precheckFile(file: Pick<File, "name" | "size">): string | null {
  const name = file.name.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return "Only PDF, DOCX and XLSX files are supported.";
  }
  if (file.size === 0) return "The file is empty.";
  if (file.size > MAX_UPLOAD_BYTES) return `Larger than ${formatBytes(MAX_UPLOAD_BYTES)}.`;
  return null;
}

import type { Tone } from "@/components/ui/badge";
import type { QuestionnaireStatus } from "@/lib/api/client";
import { formatBytes, MAX_UPLOAD_BYTES } from "@/lib/documents";

export const QUESTIONNAIRE_EXTENSIONS = [
  ".xlsx",
  ".csv",
  ".docx",
  ".pdf",
  ".xml",
  ".png",
  ".jpg",
  ".jpeg",
] as const;

export function precheckQuestionnaire(file: Pick<File, "name" | "size">): string | null {
  const name = file.name.toLowerCase();
  if (!QUESTIONNAIRE_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return "Supported: XLSX, CSV, DOCX, PDF, XML, PNG and JPEG.";
  }
  if (file.size === 0) return "The file is empty.";
  if (file.size > MAX_UPLOAD_BYTES) return `Larger than ${formatBytes(MAX_UPLOAD_BYTES)}.`;
  return null;
}

const ERRORS: Record<string, string> = {
  no_text: "No text found. If this is a scan, the OCR engine may be turned off.",
  no_questions: "No questions were found in this file.",
  bad_mapping: "The chosen columns don't match the file. Pick them again.",
  too_large: "The questionnaire is too large to import.",
  too_many_pages: "The document has more pages than the limit.",
  corrupt: "The file appears to be damaged.",
  encrypted: "The PDF is password-protected. Upload an unlocked copy.",
  vision_unavailable: "Reading scans with Claude is selected but not configured.",
  vision_failed: "The scan couldn't be read. Try again.",
  extraction_refused: "The scan couldn't be read. Try again.",
  queue_unavailable: "Processing couldn't start. Try again.",
  internal: "Something went wrong while reading the file. Try again.",
};

export function questionnaireError(code: string | null | undefined): string {
  return (code && ERRORS[code]) || "Import failed.";
}

export const QUESTIONNAIRE_STATUS: Record<QuestionnaireStatus, { label: string; tone: Tone }> = {
  queued: { label: "Queued", tone: "review" },
  extracting: { label: "Reading", tone: "review" },
  needs_mapping: { label: "Choose columns", tone: "primary" },
  ready: { label: "Ready", tone: "approved" },
  failed: { label: "Failed", tone: "manual" },
};

export function isQuestionnairePending(q: { status: QuestionnaireStatus }): boolean {
  return q.status === "queued" || q.status === "extracting";
}

export const EXTRACTOR_LABEL: Record<string, string> = {
  spreadsheet: "Spreadsheet columns",
  docx: "Word tables and paragraphs",
  "pdf-text": "PDF text layer",
  "ocr-local": "OCR (PaddleOCR, local)",
  "claude-vision": "Claude vision",
  xml: "XML elements",
};

/** Where a question sits in the original file: "CAIQ · row 12 · answer C12", "p.3", ... */
export function locatorLabel(locator: Record<string, unknown>): string {
  const parts: string[] = [];
  if (typeof locator.sheet === "string") parts.push(locator.sheet);
  if (typeof locator.table === "number") parts.push(`Table ${locator.table}`);
  if (typeof locator.row === "number") parts.push(`row ${locator.row}`);
  if (typeof locator.answer_cell === "string") parts.push(`answer ${locator.answer_cell}`);
  if (typeof locator.page === "number") parts.push(`p.${locator.page}`);
  if (typeof locator.paragraph === "number") parts.push(`¶${locator.paragraph + 1}`);
  return parts.join(" · ");
}

/** "A", "B", ... "AA": spreadsheet column names for the mapping picker. */
export function columnName(index: number): string {
  let name = "";
  let n = index + 1;
  while (n > 0) {
    const rem = (n - 1) % 26;
    name = String.fromCharCode(65 + rem) + name;
    n = Math.floor((n - 1) / 26);
  }
  return name;
}

# 0003: Document ingestion

Status: accepted (Phase 1b)

## Flow

Upload (API) → validate → store → `documents` row (`queued`) → arq job →
parse → chunk → embed → one transaction writes `document_chunks` and marks the
document `ready` (or `failed` with an `error_code`).

## Decisions

**Uploads go through the API, not straight to the bucket.** Every file is size-
checked (request body capped before parsing) and type-checked by its bytes: PDF
magic, OOXML main part, no VBA macros, zip-bomb limits. The extension alone is
never trusted. Files are ≤ 50 MB, so proxying them is cheap.

**Same bytes, same document.** `UNIQUE (org_id, sha256)`. Re-uploading returns
the existing document; another org uploading the same file gets its own copy.

**Page-accurate citations.**
- PDF: PyMuPDF text with page numbers. Headings from the PDF outline when present,
  else from font size/weight. Running headers and footers that repeat on most
  pages are removed.
- DOCX: rendered to PDF by LibreOffice in the worker (the PDF is kept as a
  "rendition" so a citation can open the page). Without LibreOffice (local dev),
  python-docx reads heading styles and Word's saved page breaks.
- XLSX: one block per row, values labelled with the header row, cited as
  sheet + row range.
- Scanned PDFs (no text layer) fail with `no_text`. OCR arrives with
  questionnaire import (ADR 0002).

**Chunks never cross a section.** ~1,500 characters for prose with a sentence
overlap, ~500 for spreadsheet rows. Each chunk stores heading path, page range
or sheet/row range. The embedded text is prefixed with document title and
heading path; the stored text is the passage alone.

**Embeddings are swappable, dimension is not.** Vectors are 1024-d (HNSW needs a
fixed dimension); Voyage and OpenAI are both asked for 1024. Each chunk records
its `embedding_model`. The `hash` provider (bag-of-words, no network) exists for
development and tests and is refused in production.

**Re-runs are idempotent.** Slow work runs outside transactions; the write
replaces all chunks for the document under a row lock. Transient embedding
errors (429/5xx) retry with backoff (4 tries); everything else fails fast with
a user-facing `error_code`. Exception messages are never stored or logged.

**Tenancy.** Both tables have forced RLS. `document_chunks` has a composite FK
`(org_id, document_id) → documents(org_id, id)`, so a chunk can't be attached to
another org's document even by a bug that sets the wrong `org_id`. Tests prove
a vector nearest-neighbour query with no WHERE clause never returns another
org's chunk, even an exact match (`tests/tenancy/test_rls.py`).

**Storage.** Keys are built from ids (`orgs/{org}/documents/{doc}/original.ext`).
R2 encrypts at rest; S3/MinIO use SSE-S3. Downloads are 5-minute signed URLs
with `Content-Disposition: attachment`; each one is audit-logged.

**Deletion is real.** Deleting a document removes the row, its chunks (cascade)
and its stored files. The audit log keeps the event, without the file name.

## Not yet

- Antivirus scanning of uploads (add ClamAV in the worker before GA).
- OCR for scanned evidence.
- Re-embedding job for a provider/model change.

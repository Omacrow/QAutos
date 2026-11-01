# ADR 0002: Confidence scoring and questionnaire extraction (planned)

**Status:** proposed (Phases 2–3). The extraction section is superseded by
[ADR 0005](0005-questionnaire-import.md): local OCR by default, Claude vision optional, no Docling.

## Confidence

The LLM's own confidence is never used as the score. The score is computed from
signals we can measure:

1. **Retrieval gate (before generation).** Hybrid retrieval (pgvector + full-text,
   fused by reciprocal rank) is followed by a reranker. If the top rerank score is
   below the org's `manual_threshold`, the question is marked **Needs manual
   answer** and no model is called.
2. **Answer Library.** A near-exact match to an approved answer is reused with its
   citations. A weaker match is passed to the model as evidence.
3. **Constrained generation.** Each claim must cite retrieved passage ids. Unknown
   ids are rejected.
4. **Independent check.** A separate call labels each claim supported, partial or
   unsupported, using only the passages that claim cites.
5. **Score** = `100 × (w1·rerank + w2·support_ratio + w3·library_agreement + w4·coverage)`,
   with caps: any unsupported claim caps the score at 50, and no citations means 0.
   If the final score is below `manual_threshold`, the draft is discarded.
6. **Reason.** The one-line reason is built from these signals, not written by the LLM.
7. **Calibration.** Weights and thresholds are stored in `organizations.settings`.
   Reviewers' approve/edit/reject outcomes will be used to fit the weights.

## Questionnaire extraction

Inputs may be XLSX, CSV, DOCX, XML, PDF, scanned PDFs or images (PNG, JPEG).

- **Structured** (XLSX/CSV/XML/DOCX tables): parse directly. The user confirms a
  column mapping (question / answer / comment), which drives export back into the
  same cells.
- **PDF and images:** a pluggable `Extractor` interface. The default is
  **Docling**, which handles layout, table structure and OCR locally. Pages with
  low confidence fall back to **Claude vision**. Tesseract alone is weak on
  tables; PaddleOCR is heavy.
- **Export limitation:** scanned PDFs and images can't be written back into the
  pixels. Those exports are an answer sheet (XLSX/DOCX) in the original question
  order, or a filled form when the PDF has AcroForm fields.

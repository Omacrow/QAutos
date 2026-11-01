# 0005: Questionnaire import

Status: accepted (Phase 2a). Supersedes the extraction part of ADR 0002.

## Goal

Turn an uploaded questionnaire, in any format, into an ordered list of questions,
each with its section, reference ("IAM-14.1") and **locator**: where its answer goes
in the original file (sheet + cell, DOCX table + row + column, paragraph, page or
XML path). The locator is what lets Phase 3 export answers back into the same file.

## Readers

| Format | How |
|---|---|
| XLSX, CSV | Find the header row (first 30 rows) and classify columns: question, answer, ref, comment. One question per row; rows that only label a domain become sections. |
| DOCX | Tables as grids (same column logic); numbered or "Describe..." paragraphs outside tables; heading styles give sections. |
| PDF with text | Text lines with font size/weight (running headers/footers removed), then the line classifier. |
| Scanned PDF, PNG, JPEG | Local OCR, then the same line classifier. |
| XML | `defusedxml` (DTDs and entities refused); question-like elements, `id`/`ref` attributes, section names. |

When no header names a question column, the questionnaire stops at
**needs_mapping** and the user picks the columns from a preview (including "no
header row"). Their choice is stored and re-used on re-extraction.

## Local models first, Claude optional

QAutos is an ML project, so every model-backed step defaults to a local or open
model and treats the Claude API as an optional engine.

- **OCR:** RapidOCR, which runs PaddleOCR's detection and recognition models on
  ONNX Runtime: CPU-only, offline, no PyTorch. Small images are upscaled before
  detection (it missed lines below ~2,400 px); OCR text is repaired for the
  model's common slips (dropped spaces, l/I) with word-frequency segmentation.
- **Question detection:** a `LineClassifier` interface. The current
  implementation is rule-based (the baseline). A trained classifier plugs into
  the same interface and is compared on the same benchmark.
- **Claude vision** (`QUESTIONNAIRE_OCR=claude`): reads scans directly and
  returns structured JSON; only with an API key.

Docling (proposed in ADR 0002) was dropped as the default: it brings PyTorch and
model files (gigabytes) into the worker image for no measured gain here.

## Measuring it

`scripts/make_test_corpus.py` generates a corpus for a fictional vendor: evidence
documents plus 12 questionnaires in every format, each with an answer key.
`scripts/eval_extraction.py` reports precision/recall per file (fuzzy match ≥ 0.9).

| Run (2026-11-01) | Precision | Recall |
|---|---|---|
| First baseline | 0.937 | 0.680 |
| + header/ID column fix, shared question rule | 1.000 | 0.943 |
| + OCR repair, upscaling, user mapping for header-less sheet | 1.000 | 0.989 |

CI fails below 0.95 / 0.95 (`test_extraction_benchmark.py`). The two remaining
misses are OCR recognition failures on one long scanned line.

**Caveat:** the rules were tuned on this generated corpus, so these numbers are
optimistic. A held-out set of real questionnaires (CSA CAIQ, EDUCAUSE HECVAT, and
customer files with permission) is needed before trusting them, and is the test
set for any trained model.

## Not yet

- Trained line classifier; alternative OCR recognizers (PaddleOCR English model,
  docTR, TrOCR) compared on the benchmark.
- AcroForm PDFs (fillable fields) as a locator type.
- Export (Phase 3).

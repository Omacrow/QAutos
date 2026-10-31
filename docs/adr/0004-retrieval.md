# 0004: Retrieval

Status: accepted (Phase 1c)

## Search

`POST /v1/search` (viewer+) runs two retrievers over the org's chunks and merges them:

- **Vector:** cosine distance on HNSW, only over chunks embedded with the current
  model (vectors from another model live in a different space).
- **Keyword:** Postgres full text over heading + text. The question is stemmed and
  stop words dropped, then terms are OR-ed: requiring every word of a
  full-sentence question matched almost nothing (recall@5 0.10 → 0.95 on the
  benchmark after the change).
- **Fusion:** reciprocal rank fusion (k = 60). No score calibration needed
  between cosine similarity and text rank.
- **Rerank (optional):** Voyage `rerank-2.5` re-scores the top 30. Its 0–1 score is
  what Phase 2's evidence gate thresholds on, so production should enable it.

If the embedding provider fails, search degrades to keyword-only and says so
(`mode: "keyword_only"`) rather than erroring. A failing reranker is skipped.

Every query filters `org_id` explicitly on top of RLS. HNSW applies the filter
after its candidate scan, so a small org among many could get too few rows:
`hnsw.ef_search` is raised to 200, and on pgvector ≥ 0.8 `hnsw.iterative_scan`
keeps scanning until enough rows pass the filter.

The question is sent in the POST body: it never appears in URLs or access logs,
and it is not stored.

## Citations open the source

Results carry document, page range (or sheet + rows) and heading. "Open page"
fetches a 5-minute signed link with `Content-Disposition: inline` (PDFs only;
DOCX opens its PDF rendition) and appends `#page=N`.

## Measuring it

`sqa/retrieval/northwind_cases.json`: 20 questionnaire-style questions over the
demo documents, paraphrased so word overlap alone can't carry them, each with
the passages that would answer it. Metrics: recall@1/3/5/10 and MRR.

- CI (`test_retrieval_benchmark_meets_quality_floor`) runs it with the local hash
  embedder and fails below recall@5 0.85 / MRR 0.70, catching regressions in
  parsing, chunking or search.
- `scripts/eval_retrieval.py` runs it against any org with the real configured
  providers, to compare models and reranking before switching.

20 questions over 3 documents is a smoke test, not a benchmark of record. It
should grow with real customer-style documents (with permission) in Phase 2.

"""Hybrid search over one org's chunks.

Two retrievers, because each misses what the other finds:
- vector (semantic): "Is MFA required?" finds "phishing-resistant multi-factor
  authentication" even with no shared words;
- keyword (Postgres full text): exact terms such as "TLS 1.2", "SOC 2", control
  ids like "IAM-14.1", which embeddings blur.

Their rankings are merged with reciprocal rank fusion (RRF), which needs no
score calibration between the two. If a reranker is configured, it re-scores
the fused top candidates and has the final say.

Every query filters on org_id explicitly, on top of Postgres RLS.
"""

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import Text, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from sqa.core.logging import get_logger
from sqa.embeddings import Embedder, EmbeddingError
from sqa.models import Document, DocumentChunk
from sqa.retrieval.rerank import Reranker

log = get_logger(__name__)

CANDIDATES_PER_RETRIEVER = 40
RRF_K = 60
MAX_RERANK_CANDIDATES = 30


@dataclass(slots=True)
class Hit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_filename: str
    document_kind: str
    document_has_rendition: bool
    ordinal: int
    text: str
    heading: str | None
    page_start: int | None
    page_end: int | None
    sheet: str | None
    row_start: int | None
    row_end: int | None
    fused_score: float
    vector_similarity: float | None = None
    keyword_rank: int | None = None
    rerank_score: float | None = None


@dataclass(slots=True)
class SearchResult:
    hits: list[Hit]
    mode: Literal["hybrid", "keyword_only"]  # keyword_only: embedding provider down
    reranked: bool
    took_ms: int
    timings: dict[str, int] = field(default_factory=dict)


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[uuid.UUID]], k: int = RRF_K
) -> dict[uuid.UUID, float]:
    """score(d) = sum over rankings of 1 / (k + rank(d)), ranks starting at 1."""
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return scores


async def search(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    query: str,
    embedder: Embedder,
    reranker: Reranker | None = None,
    limit: int = 10,
    document_ids: Sequence[uuid.UUID] | None = None,
    iterative_scan: bool = False,
) -> SearchResult:
    started = time.monotonic()
    timings: dict[str, int] = {}

    def lap(name: str, since: float) -> float:
        now = time.monotonic()
        timings[name] = round((now - since) * 1000)
        return now

    scope = [DocumentChunk.org_id == org_id]
    if document_ids:
        scope.append(DocumentChunk.document_id.in_(document_ids))

    vector_ranked: list[tuple[uuid.UUID, float]] = []
    mode: Literal["hybrid", "keyword_only"] = "hybrid"
    mark = time.monotonic()
    try:
        query_vector = await embedder.embed_query(query)
    except EmbeddingError:
        log.warning("search_degraded", org_id=str(org_id))
        query_vector, mode = None, "keyword_only"
    mark = lap("embed", mark)

    if query_vector is not None:
        await _tune_vector_scan(session, iterative_scan)
        distance = DocumentChunk.embedding.cosine_distance(query_vector)
        rows = await session.execute(
            select(DocumentChunk.id, distance)
            # Vectors from another model live in a different space: skip them.
            .where(*scope, DocumentChunk.embedding_model == embedder.model)
            .order_by(distance)
            .limit(CANDIDATES_PER_RETRIEVER)
        )
        vector_ranked = [(chunk_id, 1.0 - float(d)) for chunk_id, d in rows]
        # relaxed_order iterative scans may return rows slightly out of order.
        vector_ranked.sort(key=lambda pair: pair[1], reverse=True)
    mark = lap("vector", mark)

    # Any of the question's words, not all of them: a full-sentence question
    # rarely has every word in one passage. plainto_tsquery stems and drops
    # stop words; swapping its AND for OR lets ranking reward coverage instead.
    tsquery = func.to_tsquery(
        "english",
        func.replace(func.cast(func.plainto_tsquery("english", query), Text), "&", "|"),
    )
    rank = func.ts_rank_cd(DocumentChunk.search_tsv, tsquery)
    rows = await session.execute(
        select(DocumentChunk.id)
        .where(*scope, DocumentChunk.search_tsv.op("@@")(tsquery))
        .order_by(rank.desc(), DocumentChunk.id)
        .limit(CANDIDATES_PER_RETRIEVER)
    )
    keyword_ranked = [chunk_id for (chunk_id,) in rows]
    mark = lap("keyword", mark)

    fused = reciprocal_rank_fusion([[c for c, _ in vector_ranked], keyword_ranked])
    pool = max(limit, MAX_RERANK_CANDIDATES) if reranker else limit
    candidate_ids = sorted(fused, key=lambda c: fused[c], reverse=True)[:pool]
    hits = await _load_hits(session, org_id, candidate_ids)
    similarity = dict(vector_ranked)
    keyword_position = {c: i for i, c in enumerate(keyword_ranked, start=1)}
    for hit in hits:
        hit.fused_score = fused[hit.chunk_id]
        hit.vector_similarity = similarity.get(hit.chunk_id)
        hit.keyword_rank = keyword_position.get(hit.chunk_id)
    hits.sort(key=lambda h: h.fused_score, reverse=True)

    reranked = False
    if reranker is not None and hits:
        try:
            scores = await reranker.rerank(query, [_rerank_text(h) for h in hits])
        except EmbeddingError:
            log.warning("rerank_unavailable", org_id=str(org_id))
        else:
            for hit, score in zip(hits, scores, strict=True):
                hit.rerank_score = score
            hits.sort(key=lambda h: h.rerank_score or 0.0, reverse=True)
            reranked = True
        lap("rerank", mark)

    return SearchResult(
        hits=hits[:limit],
        mode=mode,
        reranked=reranked,
        took_ms=round((time.monotonic() - started) * 1000),
        timings=timings,
    )


async def _tune_vector_scan(session: AsyncSession, iterative_scan: bool) -> None:
    """HNSW returns its top candidates *before* the org filter is applied. With
    many orgs, a small org's chunks may not be among them. pgvector 0.8+ can keep
    scanning until enough rows pass the filter; older versions get a wider beam.
    """
    await session.execute(text("SET LOCAL hnsw.ef_search = 200"))
    if iterative_scan:
        await session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))


async def _load_hits(
    session: AsyncSession, org_id: uuid.UUID, chunk_ids: list[uuid.UUID]
) -> list[Hit]:
    if not chunk_ids:
        return []
    rows = await session.execute(
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            Document.filename,
            Document.kind,
            Document.rendition_key,
            DocumentChunk.ordinal,
            DocumentChunk.text,
            DocumentChunk.heading,
            DocumentChunk.page_start,
            DocumentChunk.page_end,
            DocumentChunk.sheet,
            DocumentChunk.row_start,
            DocumentChunk.row_end,
        )
        .join(
            Document,
            (Document.id == DocumentChunk.document_id) & (Document.org_id == DocumentChunk.org_id),
        )
        .where(DocumentChunk.org_id == org_id, DocumentChunk.id.in_(chunk_ids))
    )
    return [_hit(row) for row in rows]


def _hit(row: Any) -> Hit:
    return Hit(
        chunk_id=row.id,
        document_id=row.document_id,
        document_filename=row.filename,
        document_kind=row.kind,
        document_has_rendition=row.rendition_key is not None,
        ordinal=row.ordinal,
        text=row.text,
        heading=row.heading,
        page_start=row.page_start,
        page_end=row.page_end,
        sheet=row.sheet,
        row_start=row.row_start,
        row_end=row.row_end,
        fused_score=0.0,
    )


def _rerank_text(hit: Hit) -> str:
    return f"{hit.heading}\n\n{hit.text}" if hit.heading else hit.text


async def supports_iterative_scan(session: AsyncSession) -> bool:
    """pgvector >= 0.8 has hnsw.iterative_scan."""
    version = await session.scalar(
        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    )
    if not version:
        return False
    major, minor, *_ = (int(p) for p in str(version).split("."))
    return (major, minor) >= (0, 8)

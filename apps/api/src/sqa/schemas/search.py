import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from sqa.models import DocumentKind


class SearchRequest(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=1000)]
    limit: int = Field(default=10, ge=1, le=25)
    # Restrict to these documents (e.g. "search only the SOC 2 report").
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)


class SearchHitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_filename: str
    document_kind: DocumentKind
    document_has_rendition: bool
    ordinal: int
    text: str
    heading: str | None
    page_start: int | None
    page_end: int | None
    sheet: str | None
    row_start: int | None
    row_end: int | None
    # Cosine similarity of the passage to the question (None if found by keyword only).
    vector_similarity: float | None
    # Position in the keyword ranking (None if no keyword match).
    keyword_rank: int | None
    # 0-1 relevance from the reranker, when one is configured.
    rerank_score: float | None


class SearchOut(BaseModel):
    results: list[SearchHitOut]
    mode: Literal["hybrid", "keyword_only"]
    reranked: bool
    took_ms: int

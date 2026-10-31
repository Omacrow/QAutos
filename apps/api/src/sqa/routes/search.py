"""Search the org's indexed documents.

POST, not GET: the question goes in the body, so it never appears in URLs,
browser history, proxy logs or our access log. Queries are not stored.
"""

from fastapi import APIRouter, Request

from sqa.auth.deps import TenantSession, Viewer
from sqa.core.logging import get_logger
from sqa.embeddings import Embedder
from sqa.retrieval.rerank import Reranker
from sqa.retrieval.search import search
from sqa.schemas.search import SearchHitOut, SearchOut, SearchRequest

router = APIRouter(prefix="/v1", tags=["search"])
log = get_logger(__name__)


@router.post("/search")
async def search_documents(
    body: SearchRequest, ctx: Viewer, session: TenantSession, request: Request
) -> SearchOut:
    embedder: Embedder = request.app.state.embedder
    reranker: Reranker | None = request.app.state.reranker
    result = await search(
        session,
        org_id=ctx.org_id,
        query=body.query,
        embedder=embedder,
        reranker=reranker,
        limit=body.limit,
        document_ids=body.document_ids,
        iterative_scan=request.app.state.iterative_scan,
    )
    log.info(
        "search",
        count=len(result.hits),
        duration_ms=result.took_ms,
        status=result.mode,
    )
    return SearchOut(
        results=[SearchHitOut.model_validate(h) for h in result.hits],
        mode=result.mode,
        reranked=result.reranked,
        took_ms=result.took_ms,
    )

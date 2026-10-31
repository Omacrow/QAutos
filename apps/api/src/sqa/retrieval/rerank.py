"""Optional reranking of search candidates.

A reranker reads the query and each passage together (a cross-encoder), which
judges relevance far better than comparing two separately computed vectors. Its
0-1 score is what Phase 2 thresholds on before drafting an answer.
"""

from collections.abc import Sequence
from typing import Protocol

import httpx

from sqa.core.config import Settings
from sqa.embeddings import EmbeddingError, TransientEmbeddingError


class Reranker(Protocol):
    @property
    def model(self) -> str: ...

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        """Relevance score for each document, in input order."""
        ...

    async def aclose(self) -> None: ...


class VoyageReranker:
    def __init__(self, *, model: str, client: httpx.AsyncClient) -> None:
        self._model = model
        self._client = client

    @property
    def model(self) -> str:
        return self._model

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        if not documents:
            return []
        try:
            response = await self._client.post(
                "rerank",
                json={"model": self._model, "query": query, "documents": list(documents)},
            )
        except httpx.TransportError:
            raise TransientEmbeddingError("transport") from None
        if response.status_code == 429 or response.status_code >= 500:
            raise TransientEmbeddingError(str(response.status_code))
        if response.status_code != 200:
            raise EmbeddingError(str(response.status_code))  # body may echo the query
        scores = [0.0] * len(documents)
        for item in response.json()["data"]:
            scores[item["index"]] = float(item["relevance_score"])
        return scores

    async def aclose(self) -> None:
        await self._client.aclose()


def make_reranker(settings: Settings) -> Reranker | None:
    if settings.rerank_provider == "none":
        return None
    if settings.voyage_api_key is None:
        raise RuntimeError("VOYAGE_API_KEY is required for RERANK_PROVIDER=voyage")
    client = httpx.AsyncClient(
        base_url="https://api.voyageai.com/v1/",
        headers={"Authorization": f"Bearer {settings.voyage_api_key.get_secret_value()}"},
        timeout=httpx.Timeout(30.0, connect=10.0),
    )
    return VoyageReranker(model=settings.rerank_model, client=client)

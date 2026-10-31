"""Swappable embedding providers. Model names and keys come from settings.

Every provider returns EMBEDDING_DIM-sized vectors, so switching providers
needs a re-embed but no schema change. Each chunk stores the model that
embedded it, so mixed models can be detected.

The "hash" provider is a local bag-of-words embedding for development and
tests: no network, no key, and texts sharing words land close together. It is
refused in production.
"""

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Any, Protocol

import httpx

from sqa.core.config import Settings
from sqa.models import EMBEDDING_DIM


class EmbeddingError(Exception):
    pass


class TransientEmbeddingError(EmbeddingError):
    """Rate limited or provider unavailable: worth retrying later."""


class Embedder(Protocol):
    @property
    def model(self) -> str: ...

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...

    async def aclose(self) -> None: ...


class HashEmbedder:
    model = "hash-bow-v1"

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    async def aclose(self) -> None:
        pass

    @staticmethod
    def _embed(text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIM
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % EMBEDDING_DIM
            vector[index] += 1.0 if digest[4] & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


class _HttpEmbedder:
    batch_size = 64

    def __init__(self, *, model: str, client: httpx.AsyncClient) -> None:
        self._model = model
        self._client = client

    @property
    def model(self) -> str:
        return self._model

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            out.extend(await self._call(list(texts[start : start + self.batch_size]), "document"))
        return out

    async def embed_query(self, text: str) -> list[float]:
        return (await self._call([text], "query"))[0]

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _call(self, texts: list[str], input_type: str) -> list[list[float]]:
        try:
            response = await self._client.post("embeddings", json=self._payload(texts, input_type))
        except httpx.TransportError:
            raise TransientEmbeddingError("transport") from None
        if response.status_code == 429 or response.status_code >= 500:
            raise TransientEmbeddingError(str(response.status_code))
        if response.status_code != 200:
            # The body can echo input text; never surface it.
            raise EmbeddingError(str(response.status_code))
        data = sorted(response.json()["data"], key=lambda d: d["index"])
        vectors: list[list[float]] = [d["embedding"] for d in data]
        if len(vectors) != len(texts) or any(len(v) != EMBEDDING_DIM for v in vectors):
            raise EmbeddingError("bad_response")
        return vectors

    def _payload(self, texts: list[str], input_type: str) -> dict[str, Any]:
        raise NotImplementedError


class VoyageEmbedder(_HttpEmbedder):
    """Voyage AI. Asymmetric: documents and queries are embedded differently."""

    def _payload(self, texts: list[str], input_type: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "input": texts,
            "input_type": input_type,
            "output_dimension": EMBEDDING_DIM,
        }


class OpenAIEmbedder(_HttpEmbedder):
    """OpenAI or any OpenAI-compatible endpoint (set OPENAI_BASE_URL)."""

    batch_size = 128

    def _payload(self, texts: list[str], input_type: str) -> dict[str, Any]:
        return {"model": self.model, "input": texts, "dimensions": EMBEDDING_DIM}


def make_embedder(settings: Settings) -> Embedder:
    if settings.embeddings_provider == "hash":
        return HashEmbedder()
    timeout = httpx.Timeout(60.0, connect=10.0)
    if settings.embeddings_provider == "voyage":
        if settings.voyage_api_key is None:
            raise RuntimeError("VOYAGE_API_KEY is required for EMBEDDINGS_PROVIDER=voyage")
        client = httpx.AsyncClient(
            base_url="https://api.voyageai.com/v1/",
            headers={"Authorization": f"Bearer {settings.voyage_api_key.get_secret_value()}"},
            timeout=timeout,
        )
        return VoyageEmbedder(model=settings.embeddings_model, client=client)
    if settings.openai_api_key is None:
        raise RuntimeError("OPENAI_API_KEY is required for EMBEDDINGS_PROVIDER=openai")
    client = httpx.AsyncClient(
        base_url=settings.openai_base_url.rstrip("/") + "/",
        headers={"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"},
        timeout=timeout,
    )
    return OpenAIEmbedder(model=settings.embeddings_model, client=client)

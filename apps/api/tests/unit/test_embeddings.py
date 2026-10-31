import json
import math

import httpx
import pytest

from sqa.core.config import Settings
from sqa.embeddings import (
    EmbeddingError,
    HashEmbedder,
    OpenAIEmbedder,
    TransientEmbeddingError,
    VoyageEmbedder,
)
from sqa.models import EMBEDDING_DIM


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def test_hash_embedder_is_deterministic_and_normalized() -> None:
    embedder = HashEmbedder()
    a, b = await embedder.embed_documents(["Backups are encrypted", "Backups are encrypted"])
    assert a == b
    assert len(a) == EMBEDDING_DIM
    assert math.isclose(math.sqrt(sum(v * v for v in a)), 1.0)


async def test_hash_embedder_shared_words_are_closer() -> None:
    embedder = HashEmbedder()
    query = await embedder.embed_query("are backups encrypted at rest")
    near, far = await embedder.embed_documents(
        ["Backups are encrypted at rest with AES-256", "The office has a coffee machine"]
    )
    assert _cosine(query, near) > _cosine(query, far)


def _fake_api(captured: list[dict[str, object]], status: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured.append(payload)
        if status != 200:
            return httpx.Response(status, json={"detail": "echoes the input text"})
        data = [
            {"index": i, "embedding": [0.0] * EMBEDDING_DIM} for i in range(len(payload["input"]))
        ]
        return httpx.Response(200, json={"data": list(reversed(data))})

    return httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )


async def test_voyage_batches_and_requests_fixed_dimension() -> None:
    captured: list[dict[str, object]] = []
    embedder = VoyageEmbedder(model="voyage-3.5", client=_fake_api(captured))
    vectors = await embedder.embed_documents([f"t{i}" for i in range(130)])
    assert len(vectors) == 130
    assert [len(c["input"]) for c in captured] == [64, 64, 2]  # type: ignore[arg-type]
    assert captured[0]["input_type"] == "document"
    assert captured[0]["output_dimension"] == EMBEDDING_DIM
    await embedder.embed_query("q")
    assert captured[-1]["input_type"] == "query"


async def test_openai_requests_fixed_dimension() -> None:
    captured: list[dict[str, object]] = []
    embedder = OpenAIEmbedder(model="text-embedding-3-small", client=_fake_api(captured))
    await embedder.embed_documents(["a"])
    assert captured[0] == {"model": "text-embedding-3-small", "input": ["a"], "dimensions": 1024}


@pytest.mark.parametrize(
    ("status", "error"),
    [(429, TransientEmbeddingError), (503, TransientEmbeddingError), (400, EmbeddingError)],
)
async def test_provider_errors(status: int, error: type[Exception]) -> None:
    embedder = VoyageEmbedder(model="m", client=_fake_api([], status=status))
    with pytest.raises(error) as exc:
        await embedder.embed_documents(["secret customer text"])
    assert "secret" not in str(exc.value)
    assert "echoes" not in str(exc.value)


@pytest.mark.parametrize(
    "override",
    [
        {"embeddings_provider": "hash"},
        {"storage_backend": "local"},
        {"queue_backend": "inline"},
        {"redis_url": "memory://", "queue_backend": "inline"},
    ],
)
def test_production_refuses_dev_backends(override: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="development only"):
        Settings(
            environment="production",
            database_url="postgresql://u:p@h/d",  # type: ignore[arg-type]
            clerk_issuer="https://x",
            **override,  # type: ignore[arg-type]
        )

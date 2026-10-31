"""Search over HTTP, tenant isolation for search, and the retrieval quality floor."""

import uuid
from collections.abc import Iterator, Sequence

import pytest
from fakeredis import FakeAsyncRedis
from fastapi.testclient import TestClient

from sqa.auth.clerk import ClerkVerifier
from sqa.core.config import Settings
from sqa.db.session import Database
from sqa.embeddings import EmbeddingError, HashEmbedder
from sqa.main import create_app
from tests.conftest import MintToken
from tests.samples import make_pdf
from tests.tenancy.test_api_isolation import _auth

pytestmark = pytest.mark.db


@pytest.fixture
def client(app_settings: Settings, verifier: ClerkVerifier) -> Iterator[TestClient]:
    app = create_app(app_settings, verifier=verifier, redis=FakeAsyncRedis())
    with TestClient(app) as c:
        yield c


def _org_headers(mint_token: MintToken, role: str = "org:admin") -> dict[str, str]:
    return _auth(mint_token(user_id="u", org_id=f"org_{uuid.uuid4().hex[:8]}", role=role))


def _upload(client: TestClient, headers: dict[str, str], lines: list[tuple[str, str]]) -> str:
    """One page per (heading, body) pair. Returns the document id."""
    data = make_pdf([[(h, 16, True), (body, 10.5, False)] for h, body in lines])
    response = client.post(
        "/v1/documents",
        headers=headers,
        files={"file": (f"{uuid.uuid4().hex[:6]}.pdf", data, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["document"]["status"] == "ready"
    doc_id: str = response.json()["document"]["id"]
    return doc_id


def _search(client: TestClient, headers: dict[str, str], query: str, **extra: object) -> dict:  # type: ignore[type-arg]
    response = client.post("/v1/search", headers=headers, json={"query": query, **extra})
    assert response.status_code == 200, response.text
    body: dict = response.json()  # type: ignore[type-arg]
    return body


POLICY = [
    ("Encryption", "Customer data at rest is encrypted with AES-256 keys rotated yearly."),
    ("Access Control", "Phishing-resistant multi-factor authentication is required for staff."),
    ("Backups", "Backups are restored in a monthly test and kept for 35 days."),
]


def test_search_returns_cited_passages(client: TestClient, mint_token: MintToken) -> None:
    headers = _org_headers(mint_token)
    doc_id = _upload(client, headers, POLICY)
    body = _search(client, headers, "Is MFA required for employees? multi-factor authentication")
    assert body["mode"] == "hybrid"
    assert body["reranked"] is False
    top = body["results"][0]
    assert top["heading"] == "Access Control"
    assert (top["page_start"], top["page_end"]) == (2, 2)
    assert top["document_id"] == doc_id
    assert top["document_kind"] == "pdf"
    assert top["keyword_rank"] == 1
    assert top["vector_similarity"] is not None


def test_search_never_crosses_tenants(client: TestClient, mint_token: MintToken) -> None:
    a = _org_headers(mint_token)
    b = _org_headers(mint_token)
    _upload(client, a, [("Secrets", "The zebra-falcon rotation key lives in vault seven.")])
    _upload(client, b, [("Other", "Unrelated text about office plants.")])

    found_a = _search(client, a, "zebra-falcon rotation key vault")
    assert found_a["results"], "owner org should find its own passage"
    found_b = _search(client, b, "zebra-falcon rotation key vault")
    assert all("zebra" not in r["text"] for r in found_b["results"])

    # Asking for org A's document id from org B returns nothing, not A's chunks.
    a_doc = found_a["results"][0]["document_id"]
    assert _search(client, b, "zebra-falcon", document_ids=[a_doc])["results"] == []


def test_search_can_be_limited_to_documents(client: TestClient, mint_token: MintToken) -> None:
    headers = _org_headers(mint_token)
    first = _upload(client, headers, [("Backups", "Backups are encrypted and tested monthly.")])
    second = _upload(client, headers, [("Backups", "Backups are kept offsite for a year.")])
    body = _search(client, headers, "backups", document_ids=[second])
    assert {r["document_id"] for r in body["results"]} == {second}
    assert first not in {r["document_id"] for r in body["results"]}


def test_search_falls_back_to_keywords_when_embeddings_fail(
    client: TestClient, mint_token: MintToken
) -> None:
    class Down(HashEmbedder):
        async def embed_query(self, text: str) -> list[float]:
            raise EmbeddingError("503")

    headers = _org_headers(mint_token)
    _upload(client, headers, POLICY)
    client.app.state.embedder = Down()  # type: ignore[attr-defined]
    body = _search(client, headers, "AES-256 encryption at rest")
    assert body["mode"] == "keyword_only"
    assert body["results"][0]["heading"] == "Encryption"
    assert body["results"][0]["vector_similarity"] is None


def test_reranker_has_the_final_say(client: TestClient, mint_token: MintToken) -> None:
    class PreferBackups:
        model = "fake-rerank"

        async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
            return [0.95 if "Backups" in d else 0.1 for d in documents]

        async def aclose(self) -> None:
            pass

    headers = _org_headers(mint_token)
    _upload(client, headers, POLICY)
    client.app.state.reranker = PreferBackups()  # type: ignore[attr-defined]
    body = _search(client, headers, "encryption keys")
    assert body["reranked"] is True
    assert body["results"][0]["heading"] == "Backups"
    assert body["results"][0]["rerank_score"] == 0.95


@pytest.mark.parametrize(
    "payload",
    [{"query": ""}, {"query": " a "}, {"query": "x" * 1001}, {"query": "ok?", "limit": 99}],
)
def test_search_validates_input(client: TestClient, mint_token: MintToken, payload: dict) -> None:  # type: ignore[type-arg]
    assert (
        client.post("/v1/search", headers=_org_headers(mint_token), json=payload).status_code == 422
    )


def test_search_requires_auth_and_allows_viewers(client: TestClient, mint_token: MintToken) -> None:
    assert client.post("/v1/search", json={"query": "backups"}).status_code == 401
    viewer = _org_headers(mint_token, role="org:member")
    assert client.post("/v1/search", headers=viewer, json={"query": "backups"}).status_code == 200


def test_search_with_only_stop_words_returns_cleanly(
    client: TestClient, mint_token: MintToken
) -> None:
    headers = _org_headers(mint_token)
    _upload(client, headers, POLICY)
    assert _search(client, headers, "is it the?")["mode"] == "hybrid"


# --- Quality floor ------------------------------------------------------------------

# Measured on 2026-10-31 with the local hash embedder (no reranker):
# recall@5 0.90, MRR 0.80. The floor sits a little below so noise doesn't flake,
# but a real regression in parsing, chunking or search fails CI.
MIN_RECALL_AT_5 = 0.85
MIN_MRR = 0.70


async def test_retrieval_benchmark_meets_quality_floor(app_settings: Settings) -> None:
    from sqa.ingestion.pipeline import make_deps
    from sqa.queue import InlineQueue
    from sqa.retrieval.evaluate import run_benchmark
    from sqa.services.demo_documents import add_sample_documents
    from sqa.storage import make_store

    db = Database(app_settings.async_database_url, pool_size=2)
    try:
        org_id = await db.ensure_org(f"bench_{uuid.uuid4().hex[:8]}", "Benchmark")
        embedder = HashEmbedder()
        store = make_store(app_settings, local_secret="x" * 32)
        queue = InlineQueue(make_deps(db, store, embedder, app_settings))
        await add_sample_documents(db, store, queue, org_id)
        report = await run_benchmark(db, org_id, embedder=embedder)
    finally:
        await db.dispose()
    misses = [r.case.id for r in report.misses]
    assert report.recall_at(5) >= MIN_RECALL_AT_5, (report.summary(), misses)
    assert report.mrr >= MIN_MRR, (report.summary(), misses)

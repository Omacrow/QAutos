import json
import uuid

import httpx
import pytest

from sqa.embeddings import EmbeddingError, TransientEmbeddingError
from sqa.retrieval.evaluate import Case, Report, Target, load_cases, score_case
from sqa.retrieval.rerank import VoyageReranker
from sqa.retrieval.search import Hit, reciprocal_rank_fusion
from sqa.storage import content_disposition


def _hit(document: str = "Policy.pdf", **overrides: object) -> Hit:
    values: dict[str, object] = {
        "chunk_id": uuid.uuid4(),
        "document_id": uuid.uuid4(),
        "document_filename": document,
        "document_kind": "pdf",
        "document_has_rendition": False,
        "ordinal": 0,
        "text": "x",
        "heading": None,
        "page_start": None,
        "page_end": None,
        "sheet": None,
        "row_start": None,
        "row_end": None,
        "fused_score": 0.0,
    }
    values.update(overrides)
    return Hit(**values)  # type: ignore[arg-type]


# --- Fusion ----------------------------------------------------------------------


def test_rrf_rewards_agreement_between_retrievers() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    scores = reciprocal_rank_fusion([[a, b, c], [b, c]], k=60)
    assert scores[b] > scores[a]  # 2nd + 1st beats 1st alone
    assert scores[a] == pytest.approx(1 / 61)
    assert scores[b] == pytest.approx(1 / 62 + 1 / 61)
    assert set(scores) == {a, b, c}


def test_rrf_with_one_empty_ranking_keeps_the_other_order() -> None:
    ids = [uuid.uuid4() for _ in range(3)]
    scores = reciprocal_rank_fusion([ids, []])
    assert sorted(scores, key=lambda i: scores[i], reverse=True) == ids


# --- Benchmark scoring -----------------------------------------------------------


def test_target_matching_by_heading_row_and_page() -> None:
    assert Target("Policy.pdf", heading="2.1").matches(
        _hit(heading="Security > 2.1 Authentication")
    )
    assert not Target("Policy.pdf", heading="2.2").matches(_hit(heading="Security > 2.1 Auth"))
    assert not Target("Other.pdf").matches(_hit())
    assert Target("A.xlsx", row=8).matches(_hit("A.xlsx", row_start=6, row_end=9))
    assert not Target("A.xlsx", row=8).matches(_hit("A.xlsx", row_start=2, row_end=5))
    assert not Target("A.xlsx", row=8).matches(_hit("A.xlsx"))
    assert Target("P.pdf", page=3).matches(_hit("P.pdf", page_start=2, page_end=4))


def test_report_metrics() -> None:
    case = Case("c", "q", (Target("Policy.pdf", heading="Right"),))
    right = _hit(heading="Right")
    wrong = _hit(heading="Wrong")
    results = [
        score_case(case, [right, wrong]),  # rank 1
        score_case(case, [wrong, wrong, right]),  # rank 3
        score_case(case, [wrong]),  # miss
        score_case(case, []),  # miss
    ]
    report = Report(results)
    assert [r.first_correct_rank for r in results] == [1, 3, None, None]
    assert report.recall_at(1) == 0.25
    assert report.recall_at(3) == 0.5
    assert report.mrr == pytest.approx((1 + 1 / 3) / 4)
    assert len(report.misses) == 2


def test_benchmark_cases_load_and_reference_sample_documents() -> None:
    from sqa.services.demo_documents import DEMO_FILES

    names = {name for name, _, _ in DEMO_FILES}
    cases = load_cases()
    assert len(cases) >= 20
    assert len({c.id for c in cases}) == len(cases)
    assert all(t.document in names for c in cases for t in c.targets)


# --- Reranker ----------------------------------------------------------------------


def _rerank_api(captured: list[dict[str, object]], status: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured.append(payload)
        if status != 200:
            return httpx.Response(status, json={"detail": "echo"})
        # Returned sorted by relevance, not input order.
        return httpx.Response(
            200,
            json={
                "data": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.2}]
            },
        )

    return httpx.AsyncClient(
        base_url="https://api.test/v1/", transport=httpx.MockTransport(handler)
    )


async def test_voyage_reranker_returns_scores_in_input_order() -> None:
    captured: list[dict[str, object]] = []
    reranker = VoyageReranker(model="rerank-2.5", client=_rerank_api(captured))
    assert await reranker.rerank("q", ["a", "b"]) == [0.2, 0.9]
    assert captured[0] == {"model": "rerank-2.5", "query": "q", "documents": ["a", "b"]}
    assert await reranker.rerank("q", []) == []


@pytest.mark.parametrize(
    ("status", "error"), [(429, TransientEmbeddingError), (401, EmbeddingError)]
)
async def test_voyage_reranker_errors(status: int, error: type[Exception]) -> None:
    reranker = VoyageReranker(model="m", client=_rerank_api([], status))
    with pytest.raises(error):
        await reranker.rerank("secret question", ["a"])


def test_inline_disposition_for_viewing_pdfs() -> None:
    assert content_disposition("a.pdf", inline=True).startswith('inline; filename="a.pdf"')
    assert content_disposition("a.pdf").startswith("attachment;")

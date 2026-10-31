"""Retrieval benchmark: does search put a correct passage near the top?

Each case is a questionnaire-style question plus the passages that would
answer it. Questions are paraphrased on purpose, so word overlap alone can't
carry the score. Metrics:
- recall@k: share of questions with at least one correct passage in the top k;
- MRR: mean of 1 / (rank of the first correct passage), 0 if none in the top 10.

Phase 2 drafts answers only from retrieved passages, so retrieval recall
bounds answer quality: run this whenever chunking, embeddings or search change.
"""

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqa.db.session import Database
from sqa.embeddings import Embedder
from sqa.retrieval.rerank import Reranker
from sqa.retrieval.search import Hit, search

CASES_PATH = Path(__file__).with_name("northwind_cases.json")
KS = (1, 3, 5, 10)


@dataclass(frozen=True, slots=True)
class Target:
    document: str
    heading: str | None = None  # substring of the chunk's heading path
    row: int | None = None  # spreadsheet row inside the chunk's row range
    page: int | None = None  # page inside the chunk's page range

    def matches(self, hit: Hit) -> bool:
        if hit.document_filename != self.document:
            return False
        if self.heading is not None and self.heading not in (hit.heading or ""):
            return False
        if self.row is not None and not (
            hit.row_start is not None
            and hit.row_end is not None
            and hit.row_start <= self.row <= hit.row_end
        ):
            return False
        return self.page is None or (
            hit.page_start is not None
            and hit.page_end is not None
            and hit.page_start <= self.page <= hit.page_end
        )


@dataclass(frozen=True, slots=True)
class Case:
    id: str
    question: str
    targets: tuple[Target, ...]


@dataclass(frozen=True, slots=True)
class CaseResult:
    case: Case
    first_correct_rank: int | None  # 1-based; None if not in the results


@dataclass(frozen=True, slots=True)
class Report:
    results: list[CaseResult]

    def recall_at(self, k: int) -> float:
        hits = sum(1 for r in self.results if r.first_correct_rank and r.first_correct_rank <= k)
        return hits / len(self.results) if self.results else 0.0

    @property
    def mrr(self) -> float:
        if not self.results:
            return 0.0
        total = sum(1 / r.first_correct_rank for r in self.results if r.first_correct_rank)
        return total / len(self.results)

    @property
    def misses(self) -> list[CaseResult]:
        return [r for r in self.results if r.first_correct_rank is None]

    def summary(self) -> dict[str, float]:
        return {f"recall@{k}": round(self.recall_at(k), 3) for k in KS} | {
            "mrr": round(self.mrr, 3)
        }


def load_cases(path: Path = CASES_PATH) -> list[Case]:
    raw: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return [
        Case(id=c["id"], question=c["question"], targets=tuple(Target(**t) for t in c["targets"]))
        for c in raw
    ]


def score_case(case: Case, hits: Sequence[Hit]) -> CaseResult:
    for rank, hit in enumerate(hits, start=1):
        if any(target.matches(hit) for target in case.targets):
            return CaseResult(case, rank)
    return CaseResult(case, None)


async def run_benchmark(
    db: Database,
    org_id: uuid.UUID,
    *,
    embedder: Embedder,
    reranker: Reranker | None = None,
    cases: Sequence[Case] | None = None,
    iterative_scan: bool = False,
) -> Report:
    """Search each case's question in `org_id` and score the top 10."""
    results = []
    for case in cases if cases is not None else load_cases():
        async with db.tenant(org_id) as session:
            found = await search(
                session,
                org_id=org_id,
                query=case.question,
                embedder=embedder,
                reranker=reranker,
                limit=max(KS),
                iterative_scan=iterative_scan,
            )
        results.append(score_case(case, found.hits))
    return Report(results)

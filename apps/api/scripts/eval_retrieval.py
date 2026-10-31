"""Run the retrieval benchmark against an org's indexed documents.

Usage (from apps/api, with the usual env vars set):
    uv run python scripts/eval_retrieval.py                 # the demo org
    uv run python scripts/eval_retrieval.py --org org_123   # any Clerk org id with the samples

The org must contain the Northwind sample documents, indexed with the
embedding model currently configured (reprocess them after switching models).
Exits non-zero if recall@5 is below --min-recall.
"""

import argparse
import asyncio
import sys

from sqa.core.config import get_settings
from sqa.db.session import Database
from sqa.embeddings import make_embedder
from sqa.retrieval.evaluate import run_benchmark
from sqa.retrieval.rerank import make_reranker
from sqa.retrieval.search import supports_iterative_scan


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", help="Clerk org id (default: the demo org)")
    parser.add_argument("--min-recall", type=float, default=0.0, help="fail below this recall@5")
    args = parser.parse_args()

    settings = get_settings()
    db = Database(settings.async_database_url, pool_size=2)
    embedder = make_embedder(settings)
    reranker = make_reranker(settings)
    try:
        org_id = await db.ensure_org(args.org or settings.demo_clerk_org_id, "eval")
        async with db.tenant_free() as session:
            iterative = await supports_iterative_scan(session)
        report = await run_benchmark(
            db, org_id, embedder=embedder, reranker=reranker, iterative_scan=iterative
        )
    finally:
        await embedder.aclose()
        if reranker is not None:
            await reranker.aclose()
        await db.dispose()

    print(f"embeddings: {embedder.model}   reranker: {reranker.model if reranker else 'none'}")
    print(f"cases: {len(report.results)}")
    for name, value in report.summary().items():
        print(f"  {name:<10} {value:.3f}")
    print("\nper question (rank of first correct passage):")
    for result in report.results:
        rank = result.first_correct_rank
        print(f"  {str(rank) if rank else '-':>3}  {result.case.id:<20} {result.case.question}")
    recall5 = report.recall_at(5)
    if recall5 < args.min_recall:
        print(f"\nFAIL: recall@5 {recall5:.3f} < {args.min_recall}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

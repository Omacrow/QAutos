"""arq worker: document ingestion.

Run with: arq sqa.worker.settings.WorkerSettings
"""

import secrets
import uuid
from typing import Any, ClassVar

from arq import Retry
from arq.connections import RedisSettings

from sqa.core.config import get_settings
from sqa.core.logging import configure_logging, get_logger
from sqa.db.session import Database
from sqa.embeddings import TransientEmbeddingError, make_embedder
from sqa.ingestion.pipeline import IngestDeps, make_deps
from sqa.ingestion.pipeline import ingest_document as run_ingest
from sqa.questionnaires.pipeline import extract_questions
from sqa.questionnaires.types import TransientExtractionError
from sqa.storage import make_store

log = get_logger(__name__)

MAX_TRIES = 4


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.environment != "development")
    db = Database(settings.async_database_url, pool_size=4)
    # The worker never signs download links, so its local-store secret is throwaway.
    store = make_store(settings, local_secret=secrets.token_urlsafe(32))
    ctx["deps"] = make_deps(db, store, make_embedder(settings), settings)
    log.info("worker_started")


async def shutdown(ctx: dict[str, Any]) -> None:
    deps: IngestDeps = ctx["deps"]
    await deps.embedder.aclose()
    await deps.db.dispose()


async def ping(_ctx: dict[str, Any]) -> str:
    return "pong"


async def ingest_document(ctx: dict[str, Any], org_id: str, document_id: str) -> str:
    attempt: int = ctx["job_try"]
    try:
        return await run_ingest(
            ctx["deps"],
            uuid.UUID(org_id),
            uuid.UUID(document_id),
            final_attempt=attempt >= MAX_TRIES,
        )
    except TransientEmbeddingError:
        log.warning("ingest_retry", document_id=document_id, attempt=attempt)
        raise Retry(defer=20 * attempt) from None


async def extract_questionnaire(ctx: dict[str, Any], org_id: str, questionnaire_id: str) -> str:
    attempt: int = ctx["job_try"]
    try:
        return await extract_questions(
            ctx["deps"],
            uuid.UUID(org_id),
            uuid.UUID(questionnaire_id),
            final_attempt=attempt >= MAX_TRIES,
        )
    except TransientExtractionError:
        log.warning("extract_retry", job_id=questionnaire_id, attempt=attempt)
        raise Retry(defer=20 * attempt) from None


class WorkerSettings:
    functions: ClassVar[list[Any]] = [ping, ingest_document, extract_questionnaire]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(str(get_settings().redis_url))
    max_jobs = 4
    max_tries = MAX_TRIES
    job_timeout = 15 * 60
